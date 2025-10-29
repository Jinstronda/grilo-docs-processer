"""
Google Document AI Table Extraction

Extract tables from PDFs using Google Document AI Layout Parser.
"""
from .extract_tables import extract_tables_from_pdf, create_creds

__version__ = "1.0.0"
__all__ = ["extract_tables_from_pdf", "create_creds"]
