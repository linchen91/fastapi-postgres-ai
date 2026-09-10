from fastapi import FastAPI
from dotenv import load_dotenv
import os

load_dotenv()
from llmbase import get_llm
from langchain_core.messages import HumanMessage
import psycopg2
from psycopg2.extras import RealDictCursor
import uvicorn
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import TextLoader


app = FastAPI()

def get_db_connection():
    return psycopg2.connect(
        host="localhost",
        port=5432,
        user="postgres",
        password="123456",
        database="dzservice",
        cursor_factory=RealDictCursor
    )

@app.get("/")
async def read_root():
    return {"Message": "Hello FastApi"}

@app.get("/users")
async def read_users():
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT * FROM users LIMIT 10"
            cursor.execute(sql)
            return cursor.fetchall()
    finally:
        connection.close()

loader = TextLoader('state_of_the_union.txt', autodetect_encoding=True)
documents = loader.load()
text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=0)
texts = text_splitter.split_documents(documents)
embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
embedding_list = embeddings.embed_documents([t.page_content for t in texts])

print(len(embedding_list[0]))
connection = get_db_connection()
try:
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM iterms")
        count = cursor.fetchone()["count"]
        if count == 0:
            cursor.execute("ALTER SEQUENCE iterms_id_seq RESTART WITH 1")
            for i in range(len(embedding_list)):
                embedding = embedding_list[i]
                content = texts[i].page_content
                cursor.execute(
                    "INSERT INTO iterms (content, embedding) VALUES (%s, %s)",
                    (content, embedding),
                )
            connection.commit()
            print(f"Inserted {len(embedding_list)} items into iterms")
        else:
            print(f"iterms already has {count} rows, skipping insert")
finally:
    connection.close()

query = "What did the president say about Ketanji Brown Jackson"
new_embedding = embeddings.embed_query(query)

conn = get_db_connection()
cur = conn.cursor()
embedding_str = "[" + ",".join(str(x) for x in new_embedding) + "]"
#print(embedding_str)
cur.execute(""" SELECT id, content
            FROM iterms
            ORDER BY embedding <-> %s::vector
            LIMIT 5
            """, (embedding_str,))
results = cur.fetchall()
prompt = f"""Please answer user's question according to context.
    User's question: {query}

    Context:

"""
for r in results:
    prompt += f"{r['content']}\n-------------------------\n"

print(prompt)
response = get_llm(0.7).invoke([HumanMessage(content=prompt)])
print(response.content)

if __name__ == "__main__":
    uvicorn.run("test:app", host="0.0.0.0", port=8000, reload=True)