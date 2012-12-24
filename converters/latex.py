"""Notebook export to LaTeX.

This file implements a converter class for rendering IPython notebooks as
LaTeX, suitable for rendering by pdflatex.
"""
#-----------------------------------------------------------------------------
# Copyright (c) 2012, the IPython Development Team.
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file COPYING.txt, distributed with this software.
#-----------------------------------------------------------------------------

#-----------------------------------------------------------------------------
# Imports
#-----------------------------------------------------------------------------

# Stdlib imports
import os
import subprocess
import sys

# Our own imports
from .base import Converter
from .utils import markdown2latex, remove_ansi


#-----------------------------------------------------------------------------
# Globals and constants
#-----------------------------------------------------------------------------

# XXX: This is a hack that needs to be addressed in a more principled fashion.
inkscape = 'inkscape'
if sys.platform == 'darwin':
    inkscape = '/Applications/Inkscape.app/Contents/Resources/bin/inkscape'
    if not os.path.exists(inkscape):
        inkscape = None


#-----------------------------------------------------------------------------
# Class declarations
#-----------------------------------------------------------------------------

class ConverterLaTeX(Converter):
    """Converts a notebook to a .tex file suitable for pdflatex.

    Note: this converter *needs*:

    - `pandoc`: for all conversion of markdown cells.  If your notebook only
       has Raw cells, pandoc will not be needed.

    -  `inkscape`: if your notebook has SVG figures.  These need to be
       converted to PDF before inclusion in the TeX file, as LaTeX doesn't
       understand SVG natively.

    You will in general obtain much better final PDF results if you configure
    the matplotlib backend to create SVG output with

    %config InlineBackend.figure_format = 'svg'

    (or set the equivalent flag at startup or in your configuration profile).
    """
    #-------------------------------------------------------------------------
    # Class-level attributes determining the behaviour of the class but
    # probably not varying from instance to instance.
    #-------------------------------------------------------------------------
    extension = 'tex'
    # LaTeX specific class configuration.
    inkscape = inkscape
    documentclass = 'article'
    documentclass_options = '11pt,english'
    equation_env = 'equation*'
    heading_map = {1: r'\section',
                   2: r'\subsection',
                   3: r'\subsubsection',
                   4: r'\paragraph',
                   5: r'\subparagraph',
                   6: r'\subparagraph'}
    user_preamble = None
    exclude_cells = []
    display_data_priority = ['latex', 'pdf', 'svg', 'png', 'jpg', 'text']

    def in_env(self, environment, lines):
        """Return list of environment lines for input lines

        Parameters
        ----------
        env : string
          Name of the environment to bracket with begin/end.

        lines: """
        out = [ur'\begin{%s}' % environment]
        if isinstance(lines, basestring):
            out.append(lines)
        else:  # list
            out.extend(lines)
        out.append(ur'\end{%s}' % environment)
        return out

    def convert(self, *args, **kwargs):
        # The main body is done by the logic in the parent class, and that's
        # all we need if preamble support has been turned off.
        body = super(ConverterLaTeX, self).convert(*args, **kwargs)
        if not self.with_preamble:
            return body
        # But if preamble is on, then we need to construct a proper, standalone
        # tex file.

        # Tag the document at the top and set latex class
        final = [r'%% This file was auto-generated by IPython.',
                 r'%% Conversion from the original notebook file:',
                 r'%% {0}'.format(self.infile),
                 r'%%',
                 r'\documentclass[%s]{%s}' % (self.documentclass_options,
                                              self.documentclass),
                 '',
                 ]
        # Load our own preamble, which is stored next to the main file.  We
        # need to be careful in case the script entry point is a symlink
        myfile = os.path.realpath(__file__)
        preamble = '../preamble.tex'
        with open(os.path.join(os.path.dirname(myfile), preamble)) as f:
            final.append(f.read())

        # Load any additional user-supplied preamble
        if self.user_preamble:
            final.extend(['', '%% Adding user preamble from file:',
                          '%% {0}'.format(self.user_preamble), ''])
            with open(self.user_preamble) as f:
                final.append(f.read())

        # Include document body
        final.extend([r'\begin{document}', '',
                      body,
                      r'\end{document}', ''])
        # Return value must be a string
        return '\n'.join(final)

    def render_heading(self, cell):
        marker = self.heading_map[cell.level]
        return ['%s{%s}' % (marker, cell.source)]

    def render_code(self, cell):
        if not cell.input:
            return []

        # Cell codes first carry input code, we use lstlisting for that
        lines = [ur'\begin{codecell}']

        if 'source' not in self.exclude_cells:
            lines.extend(self.in_env('codeinput',
                                     self.in_env('lstlisting', cell.input)))
        else:
            # Empty output is still needed for LaTeX formatting
            lines.extend(self.in_env('codeinput', ''))

        outlines = []
        if 'output' not in self.exclude_cells:
            for output in cell.outputs:
                conv_fn = self.dispatch(output.output_type)
                outlines.extend(conv_fn(output))

        # And then output of many possible types; use a frame for all of it.
        if outlines:
            lines.extend(self.in_env('codeoutput', outlines))

        lines.append(ur'\end{codecell}')

        return lines

    def _img_lines(self, img_file):
        rel_img_position = os.path.relpath(img_file, self.infile_dir)
        return self.in_env('center', 
            [r'\includegraphics[width=0.7\textwidth]{%s}' % rel_img_position, 
             r'\par'])

    def _svg_lines(self, img_file):
        base_file = os.path.splitext(img_file)[0]
        pdf_file = base_file + '.pdf'
        subprocess.check_call([self.inkscape, '--export-pdf=%s' % pdf_file,
                               img_file])
        return self._img_lines(pdf_file)

    def render_markdown(self, cell):
        return [markdown2latex(cell.source)]

    def render_pyout(self, output):
        lines = []

        # output is a dictionary like object with type as a key
        if 'latex' in output:
            lines.extend(self.in_env(self.equation_env, 
                         output.latex.lstrip('$$').rstrip('$$')))
        #use text only if no latex representation is available
        elif 'text' in output:
            lines.extend(self.in_env('verbatim', output.text))

        return lines

    def render_pyerr(self, output):
        # Note: a traceback is a *list* of frames.
        return self.in_env('traceback',
                        self.in_env('verbatim',
                                 remove_ansi('\n'.join(output.traceback))))

    def render_raw(self, cell):
        if self.raw_as_verbatim:
            return self.in_env('verbatim', cell.source)
        else:
            return [cell.source]

    def _unknown_lines(self, data):
        return [r'{\vspace{5mm}\bf WARNING:: unknown cell:}'] + \
          self.in_env('verbatim', data)

    def render_display_format_text(self, output):
        return self.in_env('verbatim', output.text.strip())

    def render_display_format_html(self, output):
        return []

    def render_display_format_latex(self, output):
        return self.in_env(self.equation_env, 
                           output.latex.lstrip('$$').rstrip('$$'))

    def render_display_format_json(self, output):
        # latex ignores json
        return []

    def render_display_format_javascript(self, output):
        # latex ignores javascript
        return []
