import os
import ollama
import fitz  # PyMuPDF

# CONFIGURATION
FOLDER_PATH = r"C:\path\to\your\backed_up_pdfs"  # Use your copied backup folder path
MODEL_NAME = "llama3.1"  # The model you downloaded via Ollama

def extract_text_from_pdf(pdf_path):
    """Extracts text from the first 2 pages of a PDF."""
    text = ""
    try:
        with fitz.open(pdf_path) as doc:
            # Read first 2 pages (usually enough for dates/vendors)
            for page in doc[:2]:
                text += page.get_text()
    except Exception as e:
        print(f"Error reading {pdf_path}: {e}")
    return text.strip()

def get_new_filename(pdf_text, current_name):
    """Asks the local LLM to generate a structured filename based on content."""
    if not pdf_text:
        return None
    
    prompt = f"""
    Analyze the following text extracted from a document scan. 
    Generate a clean, standardized filename based strictly on the document details.
    
    FORMAT REQUIREMENT:
    Your response must ONLY be the filename in this exact format: YYYY-MM-DD - [Vendor or Sender Name] - [Document Type].pdf
    Do not include any introductory text, markdown, or explanations. Only output the filename.
    
    Example: 2026-03-15 - Chase Bank - Monthly Statement.pdf
    
    Document Text:
    {pdf_text[:2000]}  # Limit text length to save processing time
    """
    
    try:
        response = ollama.generate(model=MODEL_NAME, prompt=prompt)
        new_name = response['response'].strip()
        # Clean up any accidental markdown or quotes the LLM might return
        new_name = new_name.replace('`', '').replace('"', '').replace("'", "")
        if not new_name.endswith('.pdf'):
            new_name += '.pdf'
        return new_name
    except Exception as e:
        print(f"LLM Error: {e}")
        return None

def batch_rename_pdfs():
    if not os.path.exists(FOLDER_PATH):
        print("Folder path does not exist.")
        return

    print("Starting local AI batch renaming process...\n")
    
    for filename in os.listdir(FOLDER_PATH):
        if filename.lower().endswith('.pdf'):
            old_path = os.path.join(FOLDER_PATH, filename)
            
            print(f"Processing: {filename}...")
            pdf_text = extract_text_from_pdf(old_path)
            
            if pdf_text:
                new_filename = get_new_filename(pdf_text, filename)
                
                if new_filename and new_filename != filename:
                    new_path = os.path.join(FOLDER_PATH, new_filename)
                    
                    # Prevent overwriting existing files
                    if os.path.exists(new_path):
                        print(f"Skipping: {new_filename} already exists.")
                        continue
                        
                    os.rename(old_path, new_path)
                    print(f"-> Renamed to: {new_filename}\n")
                else:
                    print("-> Skipped (Could not determine better name or name matches).\n")
            else:
                print("-> Skipped (No readable text found in PDF).\n")

if __name__ == "__main__":
    batch_rename_pdfs()
