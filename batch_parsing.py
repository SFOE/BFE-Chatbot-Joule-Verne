import os
from llama_index.core import SimpleDirectoryReader
from llama_parse import LlamaParse
import httpx

api_key = os.getenv("LLAMA_CLOUD_API_KEY")

async def main():
      reader = SimpleDirectoryReader(input_dir=".\data\batches\batch_1")
      documents = reader.load_data(num_workers=4)
      
      async with httpx.AsyncClient(verify=False) as client:
            parser = LlamaParse(
                        api_key=api_key,
                        custom_client=client,
                        num_workers=2,
                        show_progress=True
                        )
            parsed_docs = await parser.aparse(documents)
            documents = parsed_docs.get_text_



if __name__=='__main__':
      import asyncio
      asyncio.run(main())


