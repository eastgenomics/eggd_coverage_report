"""
Script to generate single sample coverage report.
Takes single sample coverage stats files as input, along with the raw
coverage input file and an optional "low" coverage threshold (default 20).

Jethro Rainford 200722
"""

import argparse
import base64
import os
import sys
import tempfile
import pandas as pd
import plotly.tools as plotly_tools
import plotly
import plotly.express as px
import matplotlib.pyplot as plt
import plotly.graph_objs as go
import numpy as np
import math
import seaborn as sea

from io import BytesIO
from plotly.graph_objs import *
from plotly.offline import plot
from string import Template


class singleReport():

    def load_files(self, exon_stats, gene_stats, raw_coverage, snp_vcfs):
        """
        Load in raw coverage data, coverage stats file and template.

        Args:
            - exon_stats (file): exon stats file (from args; 
                                generated by coverage_stats_single.py)
            - gene_stats (file): gene stats file (from args; 
                                generated by coverage_stats_single.py)
            - raw_coverage (file): from args; bp coverage file used as 
                                input for coverage_stats_single.py
            - snp_vcfs (list):
        
        Returns:
            - cov_stats (df): df of coverage stats for each exon
            - cov_summary (df): df of gene level coverage
            - raw_coverage (df): raw bp coverage for each exon
            - html_template (str): string of HTML report template
        """

        # read in single sample report template
        bin_dir = os.path.dirname(os.path.abspath(__file__))
        template_dir = os.path.join(bin_dir, "../data/templates/")
        single_template = os.path.join(template_dir, "single_template.html")

        with open(single_template, 'r') as temp:
            html_template = temp.read()

        # read in exon stats file
        with open(exon_stats.name) as exon_file:
            cov_stats = pd.read_csv(exon_file, sep="\t")
        
        # read in gene stats file
        with open(gene_stats) as gene_file:
            cov_summary = pd.read_csv(gene_file, sep="\t")


        column = [
                "chrom", "exon_start", "exon_end",
                "gene", "tx", "exon", "cov_start",
                "cov_end", "cov"
                ]
        
        # read in raw coverage stats file
        with open(raw_coverage) as raw_file:
            raw_coverage = pd.read_csv(raw_file, sep="\t", names=column)
        

        if snp_vcfs:
            # SNP vcfs(s) passed
            # read in all VCF(s) and concatenate into one df
            header=["chrom", "snp_pos", "id", "ref", "alt"]
            snp_df = pd.concat((pd.read_csv(f, sep="\t", usecols=[0,1,2,3,4], comment='#', low_memory=False, header=None, names=header) for f in snp_vcfs))
        else:
            snp_df = None

        return cov_stats, cov_summary, snp_df, raw_coverage, html_template


    def build_report(self, html_template, total_stats, gene_stats, sub_20_stats, snps_low_cov, snps_high_cov, fig, all_plots, report_vals):
        """
        Build report from template and variables to write to file

        Args:
            -
        
        Returns:
            - single_report (str): HTML string of filled report 
        """

        t = Template(html_template)

        single_report = t.safe_substitute(
                            total_genes = report_vals["total_genes"],
                            threshold = report_vals["threshold"],
                            exon_issues = report_vals["exon_issues"],
                            gene_issues = report_vals["gene_issues"],
                            name = report_vals["name"],
                            sub_20_stats = sub_20_stats,
                            low_cov_plots = fig, 
                            all_plots = all_plots,
                            gene_stats = gene_stats,
                            total_stats = total_stats,
                            snps_high_cov = snps_high_cov,
                            snps_low_cov = snps_low_cov
                            )

        return single_report
    

    def snp_coverage(self, snp_df, raw_coverage, threshold):
        """
        Produces table of coverage for SNPs inside of capture regions.

        Args:
            - snp_df (df): df of all SNPs from input VCF(s)
            - raw_coverage (df): raw bp coverage for each exon
        
        Returns:
            - snps_low_cov (df): SNPs with lower coverage than threshold
            - snps_high_cov (df): SNPs with higher coverage than threshold
        """
        print("Calculating coverage of given SNPs")

        # reset indexes
        snp_df = snp_df.reset_index(drop=True)
        raw_coverage = raw_coverage.reset_index(drop=True)

        # select unique exons coordinates, coverage seperated due to size
        exons = raw_coverage[["chrom", "exon_start", "exon_end"]]\
            .drop_duplicates().reset_index(drop=True)
        
        exons_cov = raw_coverage[["gene", "exon", "chrom", "exon_start", "exon_end", "cov"]]\
            .drop_duplicates().reset_index(drop=True)

        exons["chrom"] = exons["chrom"].astype(str)
        exons_cov["chrom"] = exons_cov["chrom"].astype(str)

        #intersect all SNPs against exons to find those SNPs in capture
        snps = exons.merge(snp_df, on='chrom', how='left')
        snps = snps[(snps.snp_pos >= snps.exon_start) & (snps.snp_pos <= snps.exon_end)]

        snps = snps[["chrom", "snp_pos", "ref", "alt", "id"]].reset_index(drop=True)

        # add coverage data back to df of snps in capture
        # uses less ram than performing in one go
        snp_cov = snps.merge(exons_cov, on='chrom', how='left')

        snps_cov = snp_cov[["gene", "exon", "chrom", "snp_pos", "ref", "alt", "id", "cov"]]\
            .drop_duplicates(subset=["chrom", "snp_pos", "ref", "alt"]).reset_index(drop=True)
        
        # rename columns for displaying in report
        snps_cov.columns = ["Gene", "Exon", "Chromosome", "Position", "Ref", "Alt", "ID", "Coverage"]

        snps_cov["Coverage"] = snps_cov["Coverage"].astype(int)

        # split SNPs by coverage against threshold
        snps_low_cov = snps_cov.loc[snps_cov["Coverage"] < threshold]
        snps_high_cov = snps_cov.loc[snps_cov["Coverage"] >= threshold]

        return snps_low_cov, snps_high_cov


    def low_coverage_regions(self, cov_stats, raw_coverage, threshold):
        """
        Get regions where coverage at given threshold is <100%

        Args:
            - cov_stats (df): df of coverage stats for each exon
            - raw_coverage (df): raw bp coverage for each exon
            - threshold (int): defined threshold level (default: 20)

        Returns:
            - low_raw_cov (df): df of raw bp values for each region with 
                                coverage less than 100% at threshold
        """
        # threshold column to check at
        threshold = str(threshold)+"x"

        column = [
                "gene", "tx", "chrom", "exon", "exon_start", "exon_end",
                "min", "mean", "max",
                "10x", "20x", "30x", "50x", "100x"
                ]

        # empty df  
        low_stats = pd.DataFrame(columns=column)
        
        # get all exons with <100% coverage at given threshold
        for i, row in cov_stats.iterrows():
                if int(row[threshold]) < 100:
                    low_stats = low_stats.append(row, ignore_index=True)

        # pandas is terrible and forces floats, change back to int
        dtypes = {
          'chrom': int,
          'exon': int,
          'exon_start': int,
          'exon_end': int,
          'min': int,
          'max': int
        }

        low_stats = low_stats.astype(dtypes)
        
        # get list of tuples of genes and exons with low coverage to select out raw coverage
        low_exon_list = low_stats.reset_index()[['gene', 'exon']].values.tolist()
        low_exon_list = [tuple(l) for l in low_exon_list]

        # get raw coverage for low coverage regions to plot
        low_raw_cov = raw_coverage[raw_coverage[['gene', 'exon']].apply(tuple, axis = 1
            ).isin(low_exon_list)].reset_index()

        return low_raw_cov
    

    def low_exon_plot(self, low_raw_cov, threshold):
        """
        Plot bp coverage of exon, used for those where coverage is <20x

        Args:
            - low_raw_cov (df): df of raw coverage for exons with low coverage
            - threshold (int): defined threshold level (default: 20)
        
        Returns:
            - fig (figure): plots of low coverage regions
        """
        print("Generating plots of low covered regions")

        # get list of tuples of genes and exons to define plots
        genes = low_raw_cov.drop_duplicates(["gene", "exon"])[["gene", "exon"]].values.tolist()
        genes = [tuple(l) for l in genes]

        # sort list of genes/exons by gene and exon
        genes = sorted(genes, key=lambda element: (element[0], element[1]))

        plot_titles = [str(x[0])+" exon: "+str(x[1]) for x in genes]

        low_raw_cov["exon_len"] = low_raw_cov["exon_end"] - low_raw_cov["exon_start"]
        #low_raw_cov["label_name"] = low_raw_cov["gene"]+" exon: "+(low_raw_cov["exon"].astype(str))

        low_raw_cov["relative_position"] = low_raw_cov["exon_end"] - round(((low_raw_cov["cov_end"] + low_raw_cov["cov_start"])/2))
        
        # highest coverage value to set y axis for all plots
        max_y = max(low_raw_cov["cov"].tolist())

        # set no. rows to number of plots / number of columns to define grid
        columns = 4
        rows = math.ceil(len(genes)/4)

        # define grid to add plots to
        fig = plotly_tools.make_subplots(
                            rows=rows, cols=columns, print_grid=True, 
                            horizontal_spacing= 0.06, vertical_spacing= 0.06, 
                            subplot_titles=plot_titles)

        # counter for grid
        row_no = 1
        col_no = 1

        for gene in genes:
            # make plot for each gene / exon
            
            # counter for grid, by gets to 5th entry starts new row
            if row_no // 5 == 1:
                col_no += 1
                row_no = 1
            
            # get rows for current gene and exon
            exon_cov = low_raw_cov.loc[(low_raw_cov["gene"] == gene[0]) & (low_raw_cov["exon"] == gene[1])]

            # built list of threshold points to plot line
            yval = [threshold]*max_y

            # generate plot and threshold line to display
            if sum(exon_cov["cov"]) != 0:
                plot = go.Scatter(
                            x=exon_cov["cov_start"], y=exon_cov["cov"],
                            mode="lines",
                            hovertemplate = '<i>position: </i>%{x}'+ '<br>coverage: %{y}<br>',
                            )   
            else:
                # if any plots have no coverage, just display empty plot            
                # very hacky way by making data point transparent but ¯\_(ツ)_/¯
                plot = go.Scatter(
                                x=exon_cov["cov_start"], y=exon_cov["cov"],
                                mode="markers", marker={"opacity":0}
                                )

            threshold_line = go.Scatter(x=exon_cov["cov_start"], y=yval, hoverinfo='skip', 
                            mode="lines", line = dict(color = 'rgb(205, 12, 24)', 
                            width = 1))
                        
            # add to subplot grid
            fig.add_trace(plot, col_no, row_no)
            fig.add_trace(threshold_line, col_no, row_no)

            row_no = row_no + 1

        # update plot formatting
        fig["layout"].update(height=1750, showlegend=False)         
        fig.update_xaxes(nticks=3, ticks="", showgrid=True, tickformat=',d')
        fig.update_yaxes(title='coverage')    
        fig.update_xaxes(title='exon position', color='#FFFFFF')    

        # write plots to html string
        fig = fig.to_html(full_html=False)

        return fig


    def all_gene_plots(self, raw_coverage, threshold):
        """
        Generate full plots for each gene

        Args:
            -
        
        Returns:
            -

        """
        print("Generating full gene plots")

        raw_coverage = raw_coverage.sort_values(["gene", "exon"], ascending=[True, True])
        genes = raw_coverage.drop_duplicates(["gene"])["gene"].values.tolist()

        all_plots = ""

        for gene in genes:

            # get coverage data for current gene
            gene_cov = raw_coverage.loc[(raw_coverage["gene"] == gene)]
            # get list of exons
            exons = gene_cov.drop_duplicates(["exon"])["exon"].values.tolist()
            
            # no. plot columns = no. of exons
            column_no = len(exons)
            columns = range(min(exons), max(exons)+1)

            # make subplot grid size of no. of exons, add formatting
            fig = plt.figure()
            fig.set_figwidth(20)

            if column_no == 1:
                # handle genes with single exon and not using subplots
                    plt.plot(exon_cov["cov_start"], exon_cov["cov"])
                    plt.plot([exon_cov["exon_start"], exon_cov["exon_end"]], [threshold, threshold], color='red', linestyle='-', linewidth=1)
                    plt.xticks([])

                    ymax = max(gene_cov["cov"].tolist()) + 10
                    plt.ylim(bottom=0, top=ymax)

                    xlab = str(exon_cov["exon_end"].iloc[0] - exon_cov["exon_start"].iloc[0]) + " bp"
                    plt.xlabel(xlab)

                    title = gene + "; exon " + str(exon)
                    fig.suptitle(title)

            else:
                # generate grid with space for each exon
                grid = fig.add_gridspec(1, column_no, wspace=0)
                axs = grid.subplots(sharey=True)

                fig.suptitle(gene)

                counter = 0

                for exon in exons:
                    # get coverage data for current exon
                    exon_cov = raw_coverage.loc[(raw_coverage["gene"] == gene) & (raw_coverage["exon"] == exon)]

                    axs[counter].plot(exon_cov["cov_start"], exon_cov["cov"])
                    axs[counter].plot([exon_cov["exon_start"], exon_cov["exon_end"]], [threshold, threshold], color='red', linestyle='-', linewidth=1)
        
                    xlab = str(exon_cov["exon_end"].iloc[0] - exon_cov["exon_start"].iloc[0]) + " bp"

                    axs[counter].title.set_text(exon)
                    axs[counter].set_xlabel(xlab)

                    counter += 1

                # remove y ticks and labels for all but first plot
                for i in range(column_no):
                    if i == 0:
                        continue
                    else:
                        axs[i].yaxis.set_ticks_position('none')
                
                # strip x axis ticks and labels
                plt.setp(plt.gcf().get_axes(), xticks=[])
                
                # adjust yaxis limits
                ymax = max(gene_cov["cov"].tolist()) + 10
                plt.ylim(bottom = 0, top = ymax)

            # convert image to html string and append to one really long
            # string to insert in report
            buffer = BytesIO()
            plt.savefig(buffer, format='png')
            buffer.seek(0)
            image_png = buffer.getvalue()
            buffer.close()
            graphic = base64.b64encode(image_png)
    
            data_uri = graphic.decode('utf-8')
            img_tag = "<img src=data:image/png;base64,{0} style='max-width: 100%; object-fit: contain; ' />".format(data_uri)

            all_plots = all_plots + img_tag + "<br></br>"
            
        return all_plots


    def generate_report(self, cov_stats, cov_summary, snps_low_cov, snps_high_cov, fig, all_plots, html_template, args):
        """
        Generate single sample report from coverage stats

        Args:
            - cov_stats (df): df of coverage stats for each exon
            - cov_summary (df): df of gene level coverage
            - fig (figure): plots of low coverage regions
            - threshold (int): defined threshold level (default: 20)
        
        Returns: None

        Outputs:
            - coverage_report.html (file): HTML coverage report
        """
        print("Generating report")

        threshold = args.threshold

        column = [
                "gene", "tx", "chrom", "exon", "exon_start", "exon_end",
                "min", "mean", "max",
                "10x", "20x", "30x", "50x", "100x"
                ]
          
        sub_20x = pd.DataFrame(columns=column)
        
        # get all exons with <100% coverage at threshold 
        for i, row in cov_stats.iterrows():
                if int(row["20x"]) < 100:
                    sub_20x = sub_20x.append(row, ignore_index=True)

        # pandas is terrible and forces floats, change back to int
        dtypes = {
          'chrom': int,
          'exon': int,
          'exon_start': int,
          'exon_end': int,
          'min': int,
          'max': int
        }

        sub_20x = sub_20x.astype(dtypes)
        
        # do some excel level formatting to make table more readable
        total_stats = pd.pivot_table(cov_stats, index=["gene", "tx", "chrom", "exon", "exon_start", "exon_end"], 
                        values=["min", "mean", "max", "10x", "20x", "30x", "50x", "100x"])

        sub_20_stats = pd.pivot_table(sub_20x, index=["gene", "tx", "chrom", "exon", "exon_start", "exon_end"], 
                        values=["min", "mean", "max", "10x", "20x", "30x", "50x", "100x"])

        
        # reset index to fix formatting
        columns = ["min", "mean", "max", "10x", "20x", "30x", "50x", "100x"]

        total_stats = total_stats.reindex(columns, axis=1)
        sub_20_stats = sub_20_stats.reindex(columns, axis=1)
        total_stats.reset_index(inplace=True)
        sub_20_stats.reset_index(inplace=True)

        # get values to display in report
        total_genes = len(cov_summary["gene"])
        gene_issues = len(list(set(sub_20_stats["gene"].tolist())))
        exon_issues = len(sub_20_stats["exon"])

        # empty dict to add values for displaying in report text
        report_vals = {}
        print(str(args.sample_name))
        report_vals["name"] = str(args.sample_name)
        report_vals["total_genes"] = str(total_genes)
        report_vals["gene_issues"] = str(gene_issues)
        report_vals["threshold"] = str(threshold)
        report_vals["exon_issues"] = str(exon_issues)

        sub_20_stats['20x'] = sub_20_stats['20x'].apply(lambda x: int(x))

        # set ranges for colouring cells
        x0 = pd.IndexSlice[sub_20_stats.loc[(sub_20_stats['20x'] < 10) & (sub_20_stats['20x'] > 0)].index, '20x']
        x10 = pd.IndexSlice[sub_20_stats.loc[(sub_20_stats['20x'] < 30) & (sub_20_stats['20x'] >= 10)].index, '20x']
        x30 = pd.IndexSlice[sub_20_stats.loc[(sub_20_stats['20x'] < 50) & (sub_20_stats['20x'] >= 30)].index, '20x']
        x50 = pd.IndexSlice[sub_20_stats.loc[(sub_20_stats['20x'] < 70) & (sub_20_stats['20x'] >= 50)].index, '20x']
        x70 = pd.IndexSlice[sub_20_stats.loc[(sub_20_stats['20x'] < 90) & (sub_20_stats['20x'] >= 70)].index, '20x']
        x90 = pd.IndexSlice[sub_20_stats.loc[(sub_20_stats['20x'] < 95) & (sub_20_stats['20x'] >= 90)].index, '20x']
        x95 = pd.IndexSlice[sub_20_stats.loc[(sub_20_stats['20x'] >= 95)].index, '20x']
        
        # apply colours to coverage cell based on value, 0 is given solid red
        s = sub_20_stats.style.apply(
            lambda x: ["background-color: #d70000" if x["20x"] == 0 and idx==10 else "" for idx,v in enumerate(x)], axis=1)\
            .bar(subset=x0, color='red', vmin=0, vmax=100)\
            .bar(subset=x10, color='#990000', vmin=0, vmax=100)\
            .bar(subset=x30, color='#C82538', vmin=0, vmax=100)\
            .bar(subset=x50, color='#FF4500', vmin=0, vmax=100)\
            .bar(subset=x70, color='#FF4500', vmin=0, vmax=100)\
            .bar(subset=x90, color='#45731E', vmin=0, vmax=100)\
            .bar(subset=x95, color='#007600', vmin=0, vmax=100)\
            .set_table_attributes('table border="1" class="dataframe table table-hover table-bordered"')\

        # generate html strings from table objects to write to report
        gene_stats = cov_summary.to_html().replace('<table border="1" class="dataframe">','<table class="table table-striped">')
        total_stats = total_stats.to_html().replace('<table border="1" class="dataframe">','<table class="table table-striped">')
        sub_20_stats = s.render()

        if snps_low_cov: 
            snps_low_cov = snps_low_cov.to_html().replace('<table border="1" class="dataframe">','<table class="table table-striped">')
        else:
            snps_low_cov = "$snps_low_cov"

        if snps_high_cov:
            snps_high_cov = snps_high_cov.to_html().replace('<table border="1" class="dataframe">','<table class="table table-striped">')
        else:
            snps_high_cov =  "$snps_high_cov"

        # add tables & plots to template
        html_string = self.build_report(
                html_template,total_stats, gene_stats, sub_20_stats, 
                snps_low_cov, snps_high_cov, fig, all_plots, report_vals)

        # write report
        bin_dir = os.path.dirname(os.path.abspath(__file__))
        out_dir = os.path.join(bin_dir, "../")
        outfile = os.path.join(out_dir, args.output)

        file = open(outfile, 'w')
        file.write(html_string)
        file.close()


    def parse_args(self):
        """
        Parse cmd line arguments

        Args: None

        Returns:
            - args (arguments): args passed from cmd line
        """

        parser = argparse.ArgumentParser(
            description='Generate coverage report for a single sample.'
            )
        parser.add_argument('-e', '--exon_stats',
            help='exon stats file (from coverage_stats_single.py)', type=argparse.FileType('r'), required=True)
        parser.add_argument('-g', '--gene_stats',
            help='gene stats file (from coverage_stats_single.py)', required=True)
        parser.add_argument('-r', '--raw_coverage',
            help='raw coverage file that stats were generated from', required=True)
        parser.add_argument('-s', '--snps',
            nargs='*', help='Optional; check coverage of VCF(s) of SNPs.'
        )
        parser.add_argument('-t',
            '--threshold', nargs='?', default=20, help="threshold to define low coverage (int), if not given 20 will be used as default. Must be one of the thresholds in the input file.")
        parser.add_argument('-n',
            '--sample_name', nargs='?', help="Name of sample to display in report, if not specified this will be the prefix of the gene_stats input file."
        )
        parser.add_argument('-o',
            '--output', nargs='?', help='Output report name, if not specified the sample name from the report will be used.')

        args = parser.parse_args()

        if not args.sample_name:
            # sample name not given, use input file name
            args.sample_name = args.gene_stats.rsplit(".")[0]
        
        if not args.output:
            # output file name not given, using sample name
            args.output = args.sample_name + "_coverage_report.html"

        return args


    def main(self):
        """
        Main function to generate coverage report
        """

        # parse arguments
        args = report.parse_args()

        # read in files
        cov_stats, cov_summary, snp_df, raw_coverage, html_template = report.load_files(
                                                                args.exon_stats, 
                                                                args.gene_stats, 
                                                                args.raw_coverage,
                                                                args.snps
                                                                )
        
        if args.snps:
            # if SNP VCF(s) have been passed
            snps_low_cov, snps_high_cov = report.snp_coverage(snp_df, raw_coverage, args.threshold)
        else:
            snps_low_cov, snps_high_cov = None, None
            
        # get regions with low coverage
        low_raw_cov = report.low_coverage_regions(cov_stats, raw_coverage, args.threshold)
        
        # generate plot of sub optimal regions
        fig = report.low_exon_plot(low_raw_cov, args.threshold)
        
        # generate plots of each full gene
        all_plots = report.all_gene_plots(raw_coverage, args.threshold)

        # generate report
        report.generate_report(cov_stats, cov_summary, snps_low_cov, snps_high_cov, fig, all_plots, html_template, args)


if __name__ == "__main__":
   
    report = singleReport()

    report.main()
