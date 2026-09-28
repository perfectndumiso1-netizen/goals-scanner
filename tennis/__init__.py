"""Tennis Scanner — an independent module built beside the football scanner.

Nothing in this package imports football model code. The only shared piece is generic
infrastructure: `pdfgen.markdown_to_pdf` (Markdown → PDF), used read-only. Data sources,
models, markets, storage, reports, tracker and workflow are all separate from football.
"""
__version__ = "0.1.0"
