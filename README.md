# llm-pdf-renamer
Connect a local LLM to a folder directory to rename files based on their contents.

## Why?

Using a local LLM is the perfect solution for intelligently renaming files you don't know the contents of.  
It gives you 100% data sovereignty because your sensitive files never leave your computer, no data is sent to the cloud, and no internet connection is required. [1, 2, 3, 4] 
To do this, you need a local setup that includes an Ollama framework, a local LLM, and a Python script to connect the LLM to your local folder. [5, 6]

## The Recommended Setup

### 1. Install Ollama and a Model [7] 

Ollama is a free tool that runs AI models directly on your hardware. [8] 

* Download Ollama: Download and install it from [ollama.com](https://ollama.com).
* Download a Model: Open your terminal (or Command Prompt) and run:

```powershell
ollama run llama3.1
```

(Note: Llama 3.1 or Mistral are excellent, lightweight options for text processing.) [9, 10, 11] 

### 2. Install Required Python Libraries

Since your files are PDF scans, you need Python libraries to extract text from the images inside the PDFs (using OCR) or read embedded text, and a library to talk to Ollama. Run this in your terminal: [12] 

```powershell
pip install ollama pypdf pymupdf
```

## Running The Automation Script

You can use the following Python script to safely rename your files. It reads the first few pages of each PDF, asks your local LLM to generate a clean name, and renames the file automatically. [13] 

```powershell
python file_rename.py
```

### Why This Is Safer

* No Data Leaks: Your financial and medical data remains entirely in your computer's RAM and local storage.
* No Telemetry: Ollama does not send prompts back to a central server.
* Controlled Access: You choose exactly which folder the script can see, and it can only rename files—it contains no code to delete or upload anything.


## References

[1] [https://aicompetence.org](https://aicompetence.org/best-local-llm-tools-ai-models-on-your-pc/)  
[2] [https://www.gocodeo.com](https://www.gocodeo.com/post/local-llms-empowering-privacy-and-speed-in-ai-language-processing)  
[3] [https://dev.to](https://dev.to/sina14/your-guide-to-local-llms-ollama-deployment-models-and-use-cases-2jng)  
[4] [https://medium.com](https://medium.com/@sandeepkrajkumar/privategpt-f01a1802e442)  
[5] https://collabnix.com  
[6] [https://medium.com](https://medium.com/@jancalve/supercharge-your-shell-using-local-ai-models-with-simple-commands-602c22bbe480)  
[7] [https://www.modemguides.com](https://www.modemguides.com/blogs/ai-infrastructure/local-llm-knowledge-base-obsidian-setup-guide)  
[8] [https://pub.towardsai.net](https://pub.towardsai.net/building-a-local-rag-application-for-document-discovery-e72aee7c0ab7)  
[9] [https://python.plainenglish.io](https://python.plainenglish.io/self-hosted-llms-a-developers-guide-3cdae818dda6)  
[10] [https://levelup.gitconnected.com](https://levelup.gitconnected.com/declutter-your-spending-with-local-ai-finance-insighter-049191711f9e)  
[11] [https://www.innogpt.de](https://www.innogpt.de/en/blog/alternative-to-chatgpt)  
[12] [https://medium.com](https://medium.com/@pankaj_pandey/ultimate-guide-to-ocr-tools-for-document-processing-in-python-bebeb3011267)
[13] [https://www.reddit.com](https://www.reddit.com/r/ProductivityApps/comments/1hp1caz/aipowered_app_to_automatically_rename_files/)
