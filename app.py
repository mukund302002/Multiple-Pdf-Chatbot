

import streamlit as st
from dotenv import load_dotenv
from supabase import create_client, Client
from sentence_transformers import SentenceTransformer
import numpy as np
from sqlalchemy import create_engine
from htmlTemplates import css, bot_template, user_template
from langchain.llms import HuggingFaceHub
from PyPDF2 import PdfReader
from transformers import pipeline
from langchain.text_splitter import RecursiveCharacterTextSplitter
import requests
import re
import httpx
import logging
import os
from google.auth import default
from google.auth.transport.requests import Request
import google.generativeai as genai
# HuggingFace token
# api_token = "AIzaSyBjTX8MSFMU3XvkiKhZAJ2BHgnt3S3_MWI"

# huggingface token
load_dotenv()
DATABASE_URL = os.getenv('DATABASE_URL')

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
api_token = os.getenv('API_TOKEN')
api_key = os.getenv('API_KEY')

engine = create_engine(DATABASE_URL)
supabase_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
def test_connection():
    try:
        response = httpx.get(SUPABASE_URL)
    except Exception as e:
        st.error(f"Failed to connect to Supabase URL: {e}")

def get_pdf_text(pdf_docs):
    text = ""
    try:
        for pdf in pdf_docs:
            pdf_reader = PdfReader(pdf)
            for page in pdf_reader.pages:
                text += page.extract_text()
        text = clean_text(text)  # Clean the extracted text
    except Exception as e:
        st.error(f"Error reading PDF: {e}")
        text = None  # Set text to None in case of error
    return text

def get_text_chunks(text):
    max_chunk_size = 5000
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=max_chunk_size,
        chunk_overlap=100,
        length_function=len,
    )
    text_chunks = text_splitter.split_text(text)
    return text_chunks

def get_embeddings(text_chunks):
    model = SentenceTransformer('all-MiniLM-L6-v2')
    embeddings = model.encode(text_chunks, convert_to_tensor=True)
    return embeddings

def find_top_chunks(user_query, content, content_embeddings, top_n=3):
    model = SentenceTransformer('all-MiniLM-L6-v2')
    query_embedding = model.encode([user_query], convert_to_tensor=True)
    # If content_embeddings is empty, encode the entire content
    if len(content_embeddings) == 0:
        content_embeddings = model.encode(content, convert_to_tensor=True)

    similarities = np.dot(content_embeddings, query_embedding.T).squeeze()
    top_indices = np.argsort(similarities)[-top_n:][::-1]
    top_chunks = [content[idx] for idx in top_indices]
    return top_chunks

def clean_text(text):
    text = text.replace('\n', ' ')
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[^\w\s.,@-]', '', text)
    return text.strip()

def extract_chunks(texts):
    cleaned_chunks = [clean_text(text) for text in texts]
    return cleaned_chunks

def handle_userinput(user_question):
    id_value = st.session_state.get('id')  # Safely access session state with .get() method
    if id_value is None:
        st.error("User ID is not set. Please set your user ID first.")
        return

    response = supabase_client.table('pdfs').select('embeddings', 'content').eq('id', id_value).execute()
    if not response.data:  # Check if response data is empty
        st.error("No data found for the provided user ID.")
        return

    data = response.data[0]
    content = data.get('content', []) 
    # st.write("this is final content",content) # Safely access 'content' key
    content_embeddings = np.array(data.get('embeddings', []))  # Safely access 'embeddings' key

    if isinstance(content, str):
        try:
            content = eval(content)
        except Exception as e:
            st.error(f"Content is not in the expected format: {e}")
            return
        
    # Ensure content is a list of strings
    if not isinstance(content, list):
        content = [content]

    best_chunk = find_top_chunks(user_question, content, content_embeddings)
    best_chunk = extract_chunks(best_chunk)

    # Join the best chunks into a single string for the input
    # context = " ".join(best_chunk)
    input_text = f"You are an AI language model designed for a Retrieval-Augmented Generation (RAG) application. You will receive a query along with relevant chunks of text. Based on these chunks, generate a coherent and accurate response to the query. Query: {user_question} Relevant Chunks: {best_chunk}"
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.0-pro')

    # input_text = f"You are an AI language model and will answer the query based on the best chunk provided. Query: {user_question} Best chunk: {best_chunk}"

    # headers = {
    #     "Authorization": f"Bearer {api_token}",
    #     "Content-Type": "application/json"
    # }
    # payload = {"inputs": input_text, "parameters": {"max_length": 512, "temperature": 0.7, "repetition_penalty": 1.2}}
    output = model.generate_content(input_text)
    # response = requests.post(
    #     "https://api-inference.huggingface.co/models/google/flan-t5-large",
    #     headers=headers,
    #     json=payload
    # )
    response = output.text
    # if response.status_code == 200:
    #     response_data = response.json()
    #     if isinstance(response_data, list) and 'generated_text' in response_data[0]:
    #         response_text = response_data[0]['generated_text']
    #     else:
    #         response_text = "Sorry, I couldn't generate a response. Please try again."
    # else:
    #     response_text = f"Error: {response.status_code}. {response.content.decode('utf-8')}"

    # response_text = ' '.join(dict.fromkeys(response_text.split()))

    # Store chat history in session state
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = []

    # Append the new user question and bot response to chat history
    st.session_state.chat_history.append({"role": "user", "content": user_question})
    st.session_state.chat_history.append({"role": "bot", "content": response})

    # CSS styles for chat bubbles and icons
    st.markdown("""
        <style>
        
        .chat-box {
            border: 1px solid #ccc;
            border-radius: 10px;
            padding: 10px;
            margin: 10px 0;
            background-color: rgb(14, 17, 23);
            color: white;
        }
        .chat-icon {
            width: 24px;
            height: 24px;
            vertical-align: middle;
            margin-right: 8px;
        }
        .user-box {
            border-bottom: 1px solid #555;
            padding-bottom: 5px;
            margin-bottom: 5px;
        }
        .bot-box {
            padding-top: 5px;
        }
        </style>
        """, unsafe_allow_html=True)

    # Icons for user and bot
    bot_icon_url = "https://i.ibb.co/cN0nmSj/Screenshot-2023-05-28-at-02-37-21.png"  # Replace with your user icon URL
    user_icon_url = "https://w7.pngwing.com/pngs/178/595/png-transparent-user-profile-computer-icons-login-user-avatars-thumbnail.png"  # Replace with your bot icon URL

    # Display each question-answer pair in a single box
    st.markdown("<div class='chat-container'>", unsafe_allow_html=True)
    for i in range(0, len(st.session_state.chat_history), 2):
        user_message = st.session_state.chat_history[i]
        bot_message = st.session_state.chat_history[i + 1] if (i + 1) < len(st.session_state.chat_history) else {"content": ""}
        
        st.markdown(f"""
        <div class="chat-box">
            <div class="user-box">
                <img src="{user_icon_url}" class="chat-icon"><strong>{id_value}:</strong>
                <div>{user_message['content']}</div>
            </div>
            <div class="bot-box">
                <img src="{bot_icon_url}" class="chat-icon"><strong>Answer:</strong>
                <div>{bot_message['content']}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # # Input box for asking questions
    # user_input = st.text_input("Ask a question")

    # if user_input:
    #     st.session_state.chat_history.append({"role": "user", "content": user_input})
    #     # Placeholder for bot response
    #     bot_response = f"The response to '{user_input}' will be here."
    #     st.session_state.chat_history.append({"role": "bot", "content": bot_response})
    #     st.experimental_rerun()

def fetch_user_data(id_value):
    response = supabase_client.table('pdfs').select('id').eq('id', id_value).limit(1).execute()
    if response.data:
        return True
    else:
        st.error(f"No data found for ID, try again!: {id_value}")
        return False
    
def is_id_unique(new_id_value):
    response = supabase_client.table('pdfs').select('id').eq('id', new_id_value).execute()
    return len(response.data) == 0  # Return True if the ID is unique, False otherwise


def main():
    load_dotenv()
    st.set_page_config(page_title="Chat with multiple PDFs", page_icon=":books:")
    # old_id_value = None
    # new_id_value = None
    key_old_user = "file_uploader_old_user"
    key_new_user = "file_uploader_new_user"
    # old_user_pdf_docs = None
    # new_user_pdf_docs = None

    if "id" not in st.session_state:
        st.session_state.id = None
    if "user_pdf_docs" not in st.session_state:
        st.session_state.user_pdf_docs = None
    if "existing_content" not in st.session_state:
        st.session_state.existing_content = []
    if "pdf_processed" not in st.session_state:
        st.session_state.pdf_processed = False

    st.header("Chat with multiple PDFs :books:")
    st.subheader("Welcome to the AI-powered document chatbot!")

    with st.sidebar:
        user_type = st.radio("Are you a new user or an old user?", ("New User", "Old User","Continue with previous documents"))

        if user_type == "New User":
            new_id_value = st.text_input("Create new Username", value="")
            new_user_pdf_docs = st.file_uploader("Upload your PDFs here and click on 'Process'", accept_multiple_files=True, key=key_new_user)
            if st.button("Process Data"):
                if new_id_value and new_user_pdf_docs:
                    if is_id_unique(new_id_value):
                        with st.spinner("Processing"):
                            try:
                                raw_text = get_pdf_text(new_user_pdf_docs)
                                text_chunks = get_text_chunks(raw_text)
                                embeddings = get_embeddings(text_chunks)
                                embedding_list = embeddings.tolist()
                                st.session_state.id = new_id_value
                                data = {'id': new_id_value, 'content': text_chunks, 'embeddings': embedding_list}
                                supabase_client.table('pdfs').insert(data).execute()
                                st.session_state.pdf_processed = True
                            except Exception as e:
                                st.error(f"Error occurred in processing new ID and new PDFs: {e}")
                        st.success("Processing complete!")
                        st.write("You can now ask a question to the chatbot.")
                    else:
                        st.error("This User ID already exists. Please provide a unique ID.")
                else:
                    st.error("Please provide both ID and PDFs to proceed.")
                
        

        elif user_type == "Old User":
            old_id_value = st.text_input("Enter your old ID", value="")
            old_user_pdf_docs = st.file_uploader("Upload your PDFs and click on 'Process'", accept_multiple_files=True, key='key_old_user')

            if old_user_pdf_docs:
                st.session_state.user_pdf_docs = old_user_pdf_docs
            
            if st.button("Process"):
                st.session_state.id = old_id_value

                # Fetch existing data associated with old_id_value
                response = supabase_client.table('pdfs').select('content', 'embeddings').eq('id', st.session_state.id).execute()
                existing_data = response.data[0]
                
                # Ensure existing_content is a list
                existing_content = existing_data.get('content', [])
                if isinstance(existing_content, str):
                    existing_content = eval(existing_content)
                if not isinstance(existing_content, list):
                    existing_content = [existing_content]

                st.session_state.existing_content = existing_content
                existing_embeddings = np.array(existing_data['embeddings']) if 'embeddings' in existing_data else np.array([])

                # st.write("Fetching complete")

                if st.session_state.user_pdf_docs:
                    with st.spinner("Processing"):
                        try:
                            # st.write("Started processing")
                            new_raw_text = get_pdf_text(st.session_state.user_pdf_docs)
                            new_text_chunks = get_text_chunks(new_raw_text)
                            # new_text_chunks should be a list of strings (or text chunks)
                            # Ensure new_text_chunks is always a list of strings
                            if isinstance(new_text_chunks, str):
                                new_text_chunks = [new_text_chunks]

                            existing_content.extend(new_text_chunks)
                            
                            # combined_text_chunks = st.session_state.existing_content + new_text_chunks
                            # combined_text_chunks is now a combined list of strings (or text chunks)

                            new_embeddings = get_embeddings(new_text_chunks)
                            combined_embeddings = np.concatenate([existing_embeddings, new_embeddings], axis=0)
                            combined_embedding_list = combined_embeddings.tolist()

                            data = {
                                'id': st.session_state.id,
                                'content': existing_content,
                                'embeddings': combined_embedding_list
                            }
                            supabase_client.table('pdfs').delete().eq('id', st.session_state.id).execute()
                            supabase_client.table('pdfs').insert(data).execute()

                            st.session_state.pdf_processed = True
                        except Exception as e:
                            st.error(f"An error occurred with processing old ID and new documents: {e}")

                    st.success("You can now ask a question to the chatbot.")

                    
        elif user_type == "Continue with previous documents":
            old_id_value = st.text_input("Enter your username", value="")

            st.session_state.id = old_id_value

            if st.button("Process"):
                with st.spinner("Processing"):
                    try:
                        # Fetch existing data associated with old_id_value
                        # st.write("Started fetching existing data...")
                        response = supabase_client.table('pdfs').select('content', 'embeddings').eq('id', old_id_value).execute()
                        # st.write("Response fetched")

                        if response.data:
                            existing_data = response.data[0]
                            # st.write(f"Existing data: {existing_data}")

                            existing_content = existing_data.get('content', [])
                            # debugging
                            # st.write("YE existing content hae")
                            # st.write(existing_content)
                            existing_embeddings = np.array(existing_data.get('embeddings', []))

                            # st.write("Fetching complete")
                            st.session_state.pdf_processed = True
                        else:
                            st.error(f"No data found for the provided ID: {old_id_value}")

                    except Exception as e:
                        st.error(f"An error occurred with processing old ID and new documents: {e}")

                if st.session_state.pdf_processed:
                    st.success("You can now ask a question to the chatbot.")
                    



    if st.session_state.pdf_processed:
        user_question = st.text_input("Ask a question from your documents:")
        if st.button("Answer"):
            handle_userinput(user_question)

if __name__ == '__main__':
    main()
