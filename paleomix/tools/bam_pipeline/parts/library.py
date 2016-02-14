#!/usr/bin/python
#
# Copyright (c) 2012 Mikkel Schubert <MSchubert@snm.ku.dk>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
import os
import types

from paleomix.common.utilities import \
    safe_coerce_to_tuple

from paleomix.nodes.picard import \
    MarkDuplicatesNode
from paleomix.atomiccmd.builder import \
    apply_options
from paleomix.nodes.misc import \
    CopyOutputFilesNode
from paleomix.nodes.mapdamage import \
    MapDamagePlotNode, \
    MapDamageModelNode, \
    MapDamageRescaleNode
from paleomix.tools.bam_pipeline.nodes import \
    index_and_validate_bam
from paleomix.nodes.commands import \
    DuplicateHistogramNode, \
    FilterCollapsedBAMNode
from paleomix.nodes.validation import \
    DetectInputDuplicationNode


class Library:
    """Represents a single library in a BAM pipeline.

    Is reponsible for aggregating per-lane BAMS, removal of PCR duplicates,
    rescaling of quality-scores using mapDamage, as well as running mapDamage
    for QC purposes.

    Properties:
      name      -- Name of the libray (as specified in makefile)
      lanes     -- Tuple of lanes assosisated with the library
      options   -- Makefile options that apply to the current library
      folder    -- Folder containing files assosisated with library. Is used as
                   a prefix for files generated by this class.
      bams      -- Dictionary of BAM filenames -> nodes, for each BAM generated by
                   the Library class. Depending on options, this may either be newly
                   generated files, or the files produced by Lanes.
    """

    def __init__(self, config, target, prefix, lanes, name):
        self.name = name
        self.lanes = safe_coerce_to_tuple(lanes)
        self.options = lanes[0].options
        self.folder = os.path.dirname(self.lanes[0].folder)

        assert all((self.folder == os.path.dirname(lane.folder)) for lane in self.lanes)
        assert all((self.options == lane.options) for lane in self.lanes)

        lane_bams = self._collect_bams_by_type(self.lanes)

        pcr_duplicates = self.options["PCRDuplicates"]
        if pcr_duplicates:
            # pcr_duplicates may be "mark" or any trueish value
            lane_bams = self._remove_pcr_duplicates(config, prefix, lane_bams, pcr_duplicates)

        # At this point we no longer need to differentiate between types of reads
        files_and_nodes = self._collect_files_and_nodes(lane_bams)

        # Collect output bams, possible following rescaling
        self.bams, mapdamage_nodes \
            = self._build_mapdamage_nodes(config, target, prefix, files_and_nodes)

        nodes = [self._build_dataduplication_node(lane_bams)]
        nodes.extend(mapdamage_nodes)

        histogram_node = self._build_duphist_nodes(config, target, prefix, lane_bams)
        if histogram_node:
            nodes.append(histogram_node)

        self.nodes = tuple(nodes)

    @classmethod
    def _collect_bams_by_type(cls, lanes):
        bams = {}
        for lane in lanes:
            for key, files in lane.bams.iteritems():
                key = "collapsed" if (key == "Collapsed") else "normal"
                bams.setdefault(key, {}).update(files)

        return bams

    @classmethod
    def _collect_files_and_nodes(cls, bams):
        files_and_nodes = {}
        for dd in bams.itervalues():
            files_and_nodes.update(dd)
        return files_and_nodes

    def _remove_pcr_duplicates(self, config, prefix, bams, strategy):
        rmdup_cls = {"collapsed"  : FilterCollapsedBAMNode,
                     "normal"     : MarkDuplicatesNode}

        keep_duplicates = False
        if isinstance(strategy, types.StringTypes) and (strategy.lower() == "mark"):
            keep_duplicates = True

        # Indexing is required if we wish to calulate per-region statistics,
        index_required = (bool(prefix.get("RegionsOfInterest")) or
                          # or if we wish to run GATK, but only if we don't
                          # use a downstream rescaled BAM as input for GATK
                          (self.options["Features"]["RealignedBAM"] and not
                           self.options["RescaleQualities"]))

        results = {}
        for (key, files_and_nodes) in bams.items():
            output_filename = self.folder + ".rmdup.%s.bam" % key
            node = rmdup_cls[key](config       = config,
                                  input_bams   = files_and_nodes.keys(),
                                  output_bam   = output_filename,
                                  keep_dupes   = keep_duplicates,
                                  dependencies = files_and_nodes.values())
            validated_node = index_and_validate_bam(config, prefix, node,
                                                    create_index=index_required)

            results[key] = {output_filename : validated_node}
        return results

    def _build_mapdamage_nodes(self, config, target, prefix, files_and_nodes):
        # Messing with these does not cause the pipeline to re-do other stuff
        destination = os.path.join(config.destination,
                                   "%s.%s.mapDamage"
                                   % (target, prefix["Name"]), self.name)

        if self.options["RescaleQualities"]:
            files_and_nodes, node = \
              self._rescale_quality_scores(config=config,
                                           destination=destination,
                                           prefix=prefix,
                                           files_and_nodes=files_and_nodes)
        elif self.options["Features"]["mapDamage"]:
            # Basic run of mapDamage, only generates plots / tables
            node = self._build_mapdamage_plot_node(config=config,
                                                   destination=destination,
                                                   prefix=prefix,
                                                   files_and_nodes=files_and_nodes)

        return files_and_nodes, (node,)

    def _build_mapdamage_plot_node(self, config, destination, prefix, files_and_nodes):
        title = "mapDamage plot for library %r" % (self.name,)

        plot = MapDamagePlotNode.customize(config=config,
                                           reference=prefix["Path"],
                                           input_files=files_and_nodes.keys(),
                                           output_directory=destination,
                                           title=title,
                                           dependencies=files_and_nodes.values())
        apply_options(plot.command, self.options["mapDamage"])

        return plot.build_node()

    def _rescale_quality_scores(self, config, destination, prefix, files_and_nodes):
        output_filename = self.folder + ".rescaled.bam"

        # Generates basic plots / table files
        plot = self._build_mapdamage_plot_node(config=config,
                                               destination=destination,
                                               prefix=prefix,
                                               files_and_nodes=files_and_nodes)

        # Builds model of post-mortem DNA damage
        model = MapDamageModelNode.customize(reference=prefix["Reference"],
                                             directory=destination,
                                             dependencies=plot)
        apply_options(model.command, self.options["mapDamage"])
        model = model.build_node()

        # Rescales BAM quality scores using model built above
        scale = MapDamageRescaleNode.customize(config=config,
                                               reference=prefix["Reference"],
                                               input_files=files_and_nodes.keys(),
                                               output_file=output_filename,
                                               directory=destination,
                                               dependencies=model)
        apply_options(scale.command, self.options["mapDamage"])
        scale = scale.build_node()

        # Grab indexing and validation nodes, required by ROIs and GATK
        index_required = bool(prefix.get("RegionsOfInterest")) \
            or self.options["Features"]["RealignedBAM"]
        validate = index_and_validate_bam(config, prefix, scale,
                                          create_index=index_required)

        return {output_filename: validate}, model

    def _build_duphist_nodes(self, config, target, prefix, files_and_nodes):
        if not self.options["Features"]["DuplicateHist"]:
            return None

        input_files = []
        dependencies = []
        for values in files_and_nodes.itervalues():
            for (filename, node) in values.iteritems():
                input_files.append(filename)
                dependencies.append(node)

        folder = "%s.%s.duphist" % (target, prefix["Name"])
        destination = os.path.join(config.destination, folder,
                                   self.name + ".txt")

        return DuplicateHistogramNode(config=config,
                                      input_files=input_files,
                                      output_file=destination,
                                      dependencies=dependencies)

    def _build_dataduplication_node(self, bams):
        files_and_nodes = self._collect_files_and_nodes(bams)

        return DetectInputDuplicationNode(input_files=files_and_nodes.keys(),
                                          output_file=self.folder + ".duplications_checked",
                                          dependencies=files_and_nodes.values())
