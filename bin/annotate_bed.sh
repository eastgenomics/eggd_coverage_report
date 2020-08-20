#!/bin/bash

input_bed=""
gene_file=""
bp_coverage=""

Help()
{
   # Display Help
    echo "
    This script may be used to perform bedtools intersect commands to generate the required tsv file
    for generating single sample coverage statistics."
    echo ""
    echo "Usage:"
    echo ""
    echo "-i    Input bed file; must have columns chromosome, start position, end position, transcript."
    echo "-g    Exons nirvana file, contains required gene and exon information."
    echo "-b    Per base coverage file (output from mosdepth or similar)."
    echo "-o    Output file name prefix, will have the .tsv suffix."
    echo "-h    Print this Help."
    echo ""

}

# display help message on -h
while getopts ":i:g:b:o:h" option; do
   case $option in
        i) input_bed="$OPTARG"
        ;;
        g) gene_file="$OPTARG"
        ;;
        b) bp_coverage="$OPTARG"
        ;;
        o) outfile="$OPTARG"
        ;;
        h) # display Help
            Help
            exit 1
        ;;
        \?) # incorrect option
            echo "Error: Invalid option, please see usage below."
            Help
            exit
        ;;
        \*) # incorrect option
          
        ;;
   esac
done

# check for no and incorrect args given
if  [ -z $input_bed ] || 
    [ -z $gene_file  ] || 
    [ -z $bp_coverage ] || 
    [ -z $outfile ]; then
    
    echo "Error: Missing arguments, please see usage below."
        Help
        exit 0
fi

# add gene and exon annotation to bed file from exons nirvana tsv
bedtools intersect -a $input_bed -b $gene_file -wa -wb | awk 'OFS="\t" {if ($4 == $9) print}' | cut -f 1,2,3,8,9,10 > $(tmp).txt

# add coverage annotation from per base coverage bed file
bedtools intersect -wa -wb -a $tmp.txt -b $bp_coverage | cut -f 1,2,3,4,5,6,8,9,10 > $outfile.tsv

echo "Done. Output file: " $outfile.tsv