"""Database package - supports SQLite (local) and Supabase (cloud)."""
from database.db import DatabaseManager

__all__ = ['DatabaseManager']