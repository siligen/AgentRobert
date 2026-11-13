import os
import json
import pickle
import requests
import numpy as np
from typing import List, Dict, Any

# Third party imports
# Requirements: pip install pandas python-docx python-pptx pypdf numpy requests
import pandas as pd
from docx import Document
from pptx import Presentation
from pypdf import PdfReader

class TextParser:
    """Handles extraction of text from various file formats."""
    
    @staticmethod
    def parse(file_path: str) -> str:
        ext = os.path.splitext(file_path)[1].lower()
        
        if ext in ['.txt', '.md', '.py', '.cpp', '.xml', '.json']:
            return TextParser._read_text(file_path)
        elif ext == '.pdf':
            return TextParser._read_pdf(file_path)
        elif ext == '.docx':
            return TextParser._read_docx(file_path)
        elif ext == '.pptx':
            return TextParser._read_pptx(file_path)
        elif ext == '.csv':
            return TextParser._read_csv(file_path)
        elif ext == '.xlsx':
            return TextParser._read_xlsx(file_path)
        else:
            raise ValueError(f"Unsupported file extension: {ext}")

    @staticmethod
    def _read_text(path):
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()

    @staticmethod
    def _read_pdf(path):
        text = ""
        reader = PdfReader(path)
        for page in reader.pages:
            text += (page.extract_text() or "") + "\n"
        return text

    @staticmethod
    def _read_docx(path):
        doc = Document(path)
        return "\n".join([para.text for para in doc.paragraphs])

    @staticmethod
    def _read_pptx(path):
        text = ""
        prs = Presentation(path)
        for slide in prs.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    text += shape.text + "\n"
        return text

    @staticmethod
    def _read_csv(path):
        df = pd.read_csv(path)
        return df.to_string()

    @staticmethod
    def _read_xlsx(path):
        df = pd.read_excel(path)
        return df.to_string()


class RecursiveChunker:
    """
    Implements a recursive character text splitter.
    It attempts to split by a list of separators in order: 
    Double newlines, single newlines, spaces, and finally individual characters.
    """
    
    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 100):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = ["\n\n", "\n", " ", ""]

    def split_text(self, text: str) -> List[str]:
        return self._recursive_split(text, self.separators)

    def _recursive_split(self, text: str, separators: List[str]) -> List[str]:
        if len(text) <= self.chunk_size:
            return [text]

        # Pick the first separator that exists in the text
        separator = self.separators[-1]
        for s in self.separators:
            if s in text:
                separator = s
                break

        # Split text by the selected separator
        splits = text.split(separator)
        
        # Merge splits into chunks that fit chunk_size
        chunks = []
        current_chunk = []
        current_length = 0

        for s in splits:
            # Add separator back if it wasn't an empty string
            part = s + separator if separator != "" else s
            
            if current_length + len(part) <= self.chunk_size:
                current_chunk.append(part)
                current_length += len(part)
            else:
                # Save current chunk
                if current_chunk:
                    chunks.append("".join(current_chunk))
                
                # Start new chunk with overlap
                # For overlap, we take the end of the previous chunk
                overlap_text = "".join(current_chunk)
                overlap_start = max(0, len(overlap_text) - self.chunk_overlap)
                overlap_part = overlap_text[overlap_start:]
                
                current_chunk = [overlap_part + part]
                current_length = len(overlap_part) + len(part)
        
        if current_chunk:
            chunks.append("".join(current_chunk))
            
        # If a single part is still too large, recurse on it
        final_chunks = []
        for c in chunks:
            if len(c) > self.chunk_size and separators[0] != "":
                # This is a simplified recursive step
                final_chunks.extend(self._recursive_split(c, separators[1:]))
            else:
                final_chunks.append(c)

        return final_chunks


class OllamaEmbedder:
    """Interface for Ollama embedding API."""
    
    def __init__(self, model: str = 'nomic-embed-text', base_url: str = 'http://localhost:11434', notification_callback=None):
        self.model = model
        self.url = f"{base_url}/api/embeddings"
        self.notification_callback = notification_callback

    def embed(self, text: str) -> List[float]:
        payload = {
            "model": self.model,
            "prompt": text
        }
        try:
            response = requests.post(self.url, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()['embedding']
        except Exception as e:
            msg = f"Error calling Ollama API: {e}"
            if self.notification_callback:
                self.notification_callback(msg)
            else:
                print(msg)
            # Fallback to a zero vector of 768 dimensions (common for nomic)
            return [0.0] * 768 


class LocalVectorStore:
    """A lightweight numpy-based vector store with persistence."""
    
    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self.embeddings_path = os.path.join(storage_dir, 'embeddings.npy')
        self.metadata_path = os.path.join(storage_dir, 'metadata.pkl')
        
        if not os.path.exists(storage_dir):
            os.makedirs(storage_dir)
            
        self.embeddings = None # numpy array
        self.metadata = []      # list of strings
        self.load()

    def add(self, vector: List[float], text: str):
        vec = np.array(vector)
        if self.embeddings is None:
            self.embeddings = vec.reshape(1, -1)
        else:
            self.embeddings = np.vstack([self.embeddings, vec])
        
        self.metadata.append(text)
        self.save()

    def search(self, query_vector: List[float], top_k: int = 5) -> List[str]:
        if self.embeddings is None or len(self.metadata) == 0:
            return []
        
        q_vec = np.array(query_vector)
        
        # Normalize for Cosine Similarity
        norm_q = np.linalg.norm(q_vec)
        norm_embs = np.linalg.norm(self.embeddings, axis=1)
        
        # Handle zeros to avoid division by zero
        norm_q = norm_q if norm_q > 0 else 1.0
        norm_embs[norm_embs == 0] = 1.0
        
        similarities = np.dot(self.embeddings, q_vec) / (norm_embs * norm_q)
        
        # Get top k indices
        indices = np.argsort(similarities)[::-1][:top_k]
        return [self.metadata[i] for i in indices]

    def save(self):
        np.save(self.embeddings_path, self.embeddings)
        with open(self.metadata_path, 'wb') as f:
            pickle.dump(self.metadata, f)

    def load(self):
        if os.path.exists(self.embeddings_path) and os.path.exists(self.metadata_path):
            self.embeddings = np.load(self.embeddings_path)
            with open(self.metadata_path, 'rb') as f:
                self.metadata = pickle.load(f)


class RAGManager:
    """Main Orchestrator for the RAG Pipeline."""
    
    def __init__(self, index_dir: str = None, notification_callback=None):
        if index_dir is None:
            index_dir = os.path.join(os.getcwd(), ".rag_index")
        self.index_dir = index_dir
        self.parser = TextParser()
        self.chunker = RecursiveChunker()
        self.embedder = OllamaEmbedder(notification_callback=notification_callback)
        self.store = LocalVectorStore(storage_dir=index_dir)
        self.notification_callback = notification_callback

    def _notify(self, message):
        if self.notification_callback:
            self.notification_callback(message)
        else:
            print(message)

    def index_file(self, file_path: str):
        """Full pipeline: Parse -> Chunk -> Embed -> Store."""
        if not os.path.exists(file_path):
            self._notify(f"File not found: {file_path}")
            return

        self._notify(f"Indexing: {file_path}...")
        
        # 1. Parsing
        try:
            text = self.parser.parse(file_path)
        except Exception as e:
            self._notify(f"Failed to parse {file_path}: {e}")
            return
        
        # 2. Chunking
        chunks = self.chunker.split_text(text)
        
        # 3 & 4. Embedding and Storage
        for chunk in chunks:
            vector = self.embedder.embed(chunk)
            self.store.add(vector, chunk)
        
        self._notify(f"Successfully indexed {len(chunks)} chunks from {file_path}.")

    def retrieve_context(self, query: str, top_k: int = 5) -> str:
        """Embeds query and retrieves top_k most relevant chunks."""
        query_vector = self.embedder.embed(query)
        relevant_chunks = self.store.search(query_vector, top_k=top_k)
        
        if not relevant_chunks:
            return "NO CONTEXT FOUND: The vector store is empty or no relevant chunks matched. If you have a reference file, ensure it has been indexed using 'index_rag_file' first."
            
        return "\n\n---\n\n".join(relevant_chunks)

# API for document_engine.py
if __name__ == "__main__":
    print("RAG Manager initialized. Ready for use by document_engine.py")
