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
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
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
import sys
import datetime

import pypeline.ui as ui
from pypeline.common.text import padded_table

_TRIM_PIPELINE = (os.path.basename(sys.argv[0]) == "trim_pipeline")

def _print_header(timestamp, full_mkfile = True):
    print """# -*- mode: Yaml; -*-
# Timestamp: %s
#
# Default options
Options:
  # Sequencing platform, see SAM/BAM reference for valid values
  Platform: Illumina
  # Quality offset for PHRED scores, either 33 (Sanger/Illumina 1.8+) or 64 (Illumina 1.3+ / 1.5+)
  # This is used during adapter-trimming (AdapterRemoval) and sequence alignment (BWA)
  QualityOffset: 33
  """ % timestamp

    if full_mkfile:
        print """  # Use seed region during sequence alignment
  # Disabling the seed is recommended for aDNA alignments, as post-mortem damage
  # tends to localize in the seed region, which is expected to be of high fideltiy
  BWA_UseSeed:    yes
  # Max edit-distance (int), or missing prob under 0.02 err. rate (float)
  BWA_MaxEdit:    0.04
  # Filter hits with a mapping quality (PHRED) below this value
  BWA_MinQuality: 0

  # Filter PCR duplicates
  # Collapsed reads are filtered using Martin Kirchers FilterUnique,
  # while other reads are filtered using Picard MarkDuplicates.
  PCRDuplicates: yes

  # Exclude any type of trimmed reads from alignment/analysis
  # All reads are processed by default.
#  ExcludeReads:
#    - Single    # Single-ended reads, or PE reads where one mate was discarded
#    - Paired    # Pair-ended reads, where both reads were retained
#    - Collapsed # Overlapping pair-ended mate reads collapsed into a single read  # ExcludeReads:

  # Optional steps to perform during processing
  # To disable all features, replace with line "Features: []"
  Features:
#    - Raw BAM        # Generate BAM from the raw libraries (no indel realignment)
                     #   Location: {Destination}/{Target}.{Genome}.bam
    - Realigned BAM  # Generate indel-realigned BAM using the GATK Indel realigner
                     #   Location: {Destination}/{Target}.{Genome}.realigned.bam
    - mapDamage      # Generate mapDamage plot for each (unrealigned) library
                     #   Location: {Destination}/{Target}.{Genome}.mapDamage/{Library}/
    - Coverage       # Generate coverage information for the raw BAM (wo/ indel realignment)
                     #   Location: {Destination}/{Target}.{Genome}.coverage
    - Summary        # Generate target summary (uses statistics from raw BAM)
                     #   Location: {Destination}/{Target}.summary



Prefixes:
#    - NAME_OF_PREFIX: PATH_TO_PREFIX
#      Label: # mito or nucl
#
#
"""


_FILENAME = "SampleSheet.csv"

def read_alignment_records(filename):

    with open(filename) as records:
        header = records.readline().strip().split(",")
        for line in records:
            yield dict(zip(header, line.strip().split(",")))


def main(argv):
    records = {}
    for root in argv:
        if os.path.isdir(root):
            filename = os.path.join(root, _FILENAME)
        else:
            root, filename = os.path.split(root)[0], root

        for record in read_alignment_records(filename):
            libraries = records.setdefault(record["SampleID"], {})
            barcodes  = libraries.setdefault(record["Index"], [])

            record["Lane"] = int(record["Lane"])
            record["Path"] = os.path.join(root, "%(SampleID)s_%(Index)s_L%(Lane)03i_R{Pair}_*.fastq.gz" % record)
            barcodes.append(record)


    _print_header(timestamp   = datetime.datetime.now().isoformat(),
                  full_mkfile = (os.path.basename(sys.argv[0]) != "trim_pipeline"))
    for (sample, libraries) in records.iteritems():
        print "%s:" % sample
        print "  %s:" % sample
        for (library, barcodes) in libraries.iteritems():
            print "    %s:" % library
            for record in barcodes:
                print "      {FCID}_{Lane}: {Path}".format(**record)
            print
        print

    if not argv:
        ui.print_info("No directories specified, empty table printed:", file = sys.stderr)
        ui.print_info("\tUsage: %s [directory ...]" % sys.argv[0], file = sys.stderr)
        ui.print_info("Each directory must contain a '%s' file." % _FILENAME, file = sys.stderr)
    else:
        ui.print_info("Makefile printed. Please check for correctness and update Path column before running pipeline.", file = sys.stderr)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
