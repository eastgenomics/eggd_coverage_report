"""
Script to generate single sample coverage report.
Takes single sample coverage stats as input, along with the raw
coverage input file and an optional "low" coverage threshold (default 20).

Jethro Rainford 200722
"""

import argparse
import os
import sys
import tempfile
import pandas as pd
import plotly.tools as plotly_tools
import plotly
import plotly.express as px
import matplotlib.pyplot as plt
from plotly.offline import plot
import plotly.graph_objs as go
import numpy as np
import math

from jinja2 import Environment, FileSystemLoader
from plotly.graph_objs import *


class singleReport():

    def load_files(self, stats, raw_coverage):
        """
        Load in raw coverage data, coverage stats file and template.
        """
        # load template
        bin_dir = os.path.dirname(os.path.abspath(__file__))
        template_dir = os.path.join(bin_dir, "../data/templates/")
        env = Environment(loader = FileSystemLoader(template_dir))
        template = env.get_template('single_template.html')

        # read in coverage stats file
        with open(stats) as stats_file:
            cov_stats = pd.read_csv(stats_file, sep="\t")
        
        column = [
                "chrom", "exon_start", "exon_end",
                "gene", "tx", "exon", "cov_start",
                "cov_end", "cov"
                ]

        # read in raw coverage stats file
        with open(raw_coverage) as raw_file:
            raw_coverage = pd.read_csv(raw_file, sep="\t", names=column)
        
        return cov_stats, raw_coverage


    def report_template(self, sub_20_stats, fig):
        """
        HTML template for report
        """

        html_string = '''
        <html>
            <head>
                <link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.1/css/bootstrap.min.css">
                <style>body{ margin:0 100; background:whitesmoke; }</style>
            </head>
            <body>
                <h1>Coverage report for Twist Sample 1 (NA12878)</h1>
                <br></br>
                <h2>Exons with sub-optimal coverage</h2>
                ''' + sub_20_stats + '''
                <br></br>
                '''+ fig +'''

            </body>
        </html>'''

        return html_string
    

    def low_coverage_regions(self, cov_stats, raw_coverage, threshold):
        """
        Get regions where coverage at given threshold is <100%
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

        print(low_raw_cov)

        return low_raw_cov
    

    def low_exon_plot(self, low_raw_cov, threshold):
        """
        Plot bp coverage of exon, used for those where coverage is <20x

        Args:
            - low_raw_cov (df): df of raw coverage for exons with low coverage
        
        Returns:
            - 
        """
        # get list of tuples of genes and exons to define plots
        genes = low_raw_cov.drop_duplicates(["gene", "exon"])[["gene", "exon"]].values.tolist()
        genes = [tuple(l) for l in genes]

        genes = sorted(genes, key=lambda element: (element[0], element[1]))

        low_raw_cov["exon_len"] = low_raw_cov["exon_end"] - low_raw_cov["exon_start"]
        low_raw_cov["label_name"] = low_raw_cov["gene"]+" exon: "+(low_raw_cov["exon"].astype(str))

        low_raw_cov["relative_position"] = low_raw_cov["exon_end"] - round(((low_raw_cov["cov_end"] + low_raw_cov["cov_start"])/2))
        
        # list of gene & exons for titles
        plot_titles = list(set(low_raw_cov["label_name"].tolist()))
        
        # highest coverage value to set y axis for all plots
        max_y = max(low_raw_cov["cov"].tolist())

        # set no. rows to number of plots / number of columns to define grid
        columns = 4
        rows = math.ceil(len(genes)/4)

        # define grid to add plots to
        fig = plotly_tools.make_subplots(
                            rows=rows, cols=columns, print_grid=True, 
                            horizontal_spacing= 0.05, vertical_spacing= 0.05, 
                            subplot_titles=plot_titles, shared_yaxes='all'
                            )

        plots = []
        
        # counter for grid
        row_no = 1
        col_no = 1

        for gene in genes:
            # make plot for each gene / exon
            # counter for grid, by gets to 5th entry starts new row
            if row_no//5 == 1:
                col_no += 1
                row_no = 1

            exon_cov = low_raw_cov.loc[(low_raw_cov["gene"] == gene[0]) & (low_raw_cov["exon"] == gene[1])]

            # define treshold line
            yval = [threshold]*max_y

            # generate plot and threshold line to display
            plot = Line(x=exon_cov["cov_start"], y=exon_cov["cov"], mode="lines")
            threshold_line = Line(
                            x=exon_cov["cov_start"], y=yval, hoverinfo='skip', 
                            mode="lines", line = dict(color = 'rgb(205, 12, 24)', 
                            width = 1)
                            )
            plots.append(plot)            

            # add to subplot grid
            fig.add_trace(plot, col_no, row_no)
            fig.add_trace(threshold_line, col_no, row_no)

            row_no = row_no + 1
        

        fig["layout"].update(title="Exons with regions of sub-optimal coverage", width=2000, height=2000, showlegend=False)
        
        plotly.io.write_html(fig, "plots.html")

        fig = fig.to_html(full_html=False)

        return fig


    def generate_report(self, cov_stats, fig):
        """
        Generate single sample report from coverage stats

        Args:
            - template (file): template file to make report from
            - cov_stats (df): df of coverage stats for exons
        
        Returns: 

        """
        bin_dir = os.path.dirname(os.path.abspath(__file__))
        report = os.path.join(bin_dir, "../output/", "single_report.html")

        column = [
                "gene", "tx", "chrom", "exon", "exon_start", "exon_end",
                "min", "mean", "max",
                "10x", "20x", "30x", "50x", "100x"
                ]
          
        sub_20x = pd.DataFrame(columns=column)
        
        # get all exons with <100% coverage at 20x
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
        

        columns = ["min", "mean", "max", "10x", "20x", "30x", "50x", "100x"]

        stats = pd.pivot_table(cov_stats, index=["gene", "tx", "chrom", "exon", "exon_start", "exon_end"], 
                        values=["min", "mean", "max", "10x", "20x", "30x", "50x", "100x"])

        sub_20_stats = pd.pivot_table(sub_20x, index=["gene", "tx", "chrom", "exon", "exon_start", "exon_end"], 
                        values=["min", "mean", "max", "10x", "20x", "30x", "50x", "100x"])

        # with pd.option_context('display.max_rows', None, 'display.max_columns', None):
        #     print(stats)


        stats = stats.reindex(columns, axis=1)
        sub_20_stats = sub_20_stats.reindex(columns, axis=1)

        stats_html = sub_20_stats.to_html().replace('<table border="1" class="dataframe">','<table class="table table-striped">')

        html_string = self.report_template(stats_html, fig)

        file = open("report.html", 'w')
        file.write(html_string)
        file.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Generate coverage report for a single sample.'
        )
    parser.add_argument(
        'stats', help='stats file on which to generate report from')
    parser.add_argument(
        'raw_coverage', help='raw coverage file that stats were generated from')
    parser.add_argument(
        '--threshold', nargs='?', default=20, help="threshold to define low coverage (int), if not given 20 will be used as default")
    parser.add_argument(
        '--output', help='Output file name')
    parser.add_argument(
        '--plots', help='', nargs='?')
    args = parser.parse_args()

    # initialise
    report = singleReport()

    # read in files
    cov_stats, raw_coverage = report.load_files(args.stats, args.raw_coverage)
    
    # get regions with low coverage
    low_raw_cov = report.low_coverage_regions(cov_stats, raw_coverage, args.threshold)
    
    # generate plot of sub optimal regions
    fig = report.low_exon_plot(low_raw_cov, args.threshold)
     
    # generate report
    report.generate_report(cov_stats, fig)