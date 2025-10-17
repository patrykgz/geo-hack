import logging

import streamlit as st
from sqlalchemy import text
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from datetime import datetime
import re

logging.basicConfig()
logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=st.secrets.get("OPENAI_API_KEY") or "",
)

st.set_page_config(
    page_title="Brand Configuration",
    page_icon="👋",
)

# Authentication check
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔒 Authentication Required")
    st.markdown("Please enter the password to access this application.")

    with st.form("login_form"):
        password_input = st.text_input("Password", type="password", placeholder="Enter password")
        submit_button = st.form_submit_button("Login", type="primary")

        if submit_button:
            if password_input == st.secrets.get("APP_PASSWORD", ""):
                st.session_state.authenticated = True
                st.success("Authentication successful!")
                st.rerun()
            else:
                st.error("Incorrect password. Please try again.")

    st.stop()

# Database connection
conn = st.connection('data_db', type='sql', connect_args={
    "auth_token": st.secrets.get('TURSO_DB_KEY'),
},)
# Initialize database table
with conn.session as s:
    s.execute(text('''
        CREATE TABLE IF NOT EXISTS brand_info (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            description TEXT,
            updated_at TIMESTAMP
        );
    '''))
    s.commit()

st.write("# Welcome to AI Search Improver! 👋")

# Display current brand info
st.markdown("## Current Brand")
with conn.session as s:
    result = s.execute(text('SELECT name, url, description, updated_at FROM brand_info WHERE id = 1;'))
    current_brand = result.fetchone()

if current_brand:
    st.info(f"**{current_brand[0]}**")
    st.caption(f"URL: {current_brand[1]}")
    st.caption(f"Updated: {current_brand[3][:10] if current_brand[3] else 'N/A'}")
    if current_brand[2]:
        with st.expander("View Description"):
            st.write(current_brand[2])
else:
    st.warning("No brand configured yet. Please set up your brand below.")

# Brand configuration form
st.markdown("---")
st.markdown("## Configure Your Brand")

save_btn=None

with st.form("brand_form"):
    brand_name = st.text_input(
        "Brand Name",
        placeholder="e.g., Acme Corporation",
        help="Enter your brand or company name"
    )

    brand_url = st.text_input(
        "Brand Website URL",
        placeholder="e.g., https://example.com",
        help="Enter the full URL including https://"
    )

    col1, col2 = st.columns([1, 1])
    with col1:
        generate_btn = st.form_submit_button("Generate Description", type="primary", use_container_width=True)
    with col2:
        save_without_description = st.form_submit_button("Save Without Description", use_container_width=True)

# Handle form submission
if generate_btn or save_without_description:
    # Validation
    errors = []

    if not brand_name or not brand_name.strip():
        errors.append("Brand name is required")

    if not brand_url or not brand_url.strip():
        errors.append("Brand URL is required")
    else:
        # Validate URL format
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)

        if not url_pattern.match(brand_url.strip()):
            errors.append("Please enter a valid URL starting with http:// or https://")

    if errors:
        for error in errors:
            st.error(f"Error: {error}")
    else:
        brand_name = brand_name.strip()
        brand_url = brand_url.strip()

        if save_without_description:
            # Save without generating description
            try:
                s.execute(text('''
                    INSERT OR REPLACE INTO brand_info (id, name, url, description, updated_at)
                    VALUES (1, :name, :url, :description, :updated_at)
                '''), {
                    'name': brand_name,
                    'url': brand_url,
                    'description': None,
                    'updated_at': datetime.now().isoformat()
                })
                s.commit()
                st.success("Brand information saved successfully!")

                # Small delay to ensure database write completes
                import time
                time.sleep(0.5)

                st.rerun()
            except Exception as e:
                st.error(f"Database error: {str(e)}")
                import traceback
                st.code(traceback.format_exc())

        elif generate_btn:
            description = None

            # Step 1: Scrape website
            with st.spinner(f"Fetching content from {brand_url}..."):
                try:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                    response = requests.get(brand_url, headers=headers, timeout=10)
                    response.raise_for_status()

                    # Parse HTML
                    soup = BeautifulSoup(response.content, 'html.parser')

                    # Remove script and style elements
                    for script in soup(["script", "style", "nav", "footer"]):
                        script.decompose()

                    # Get text content
                    text_content = soup.get_text()

                    # Clean up whitespace
                    lines = (line.strip() for line in text_content.splitlines())
                    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                    text_content = ' '.join(chunk for chunk in chunks if chunk)

                    # Limit to first 3000 characters to avoid token limits
                    text_content = text_content[:3000]

                    st.success("Website content fetched successfully!")

                except requests.exceptions.RequestException as e:
                    st.error(f"Error fetching website: {str(e)}")
                    st.stop()

            # Step 2: Generate description with OpenAI
            with st.spinner("Generating brand description with AI..."):
                try:
                    # Get API key from secrets
                    api_key = st.secrets.get("OPENAI_API_KEY")

                    if not api_key or api_key == "your-openai-api-key-here":
                        st.error("OpenAI API key not configured. Please add your API key to .streamlit/secrets.toml")
                        st.stop()

                    # Call OpenAI API
                    response = client.chat.completions.create(
                        model="x-ai/grok-4-fast",
                        messages=[
                            {
                                "role": "system",
                                "content": "You are a marketing expert who writes concise, compelling brand descriptions. Create a 2-3 paragraph description that captures the essence of the brand, its value proposition, and what makes it unique."
                            },
                            {
                                "role": "user",
                                "content": f"Based on the following website content for {brand_name} ({brand_url}), write a concise brand description:\n\n{text_content}"
                            }
                        ]
                    )

                    print('json: ', response.model_dump_json())

                    description = response.choices[0].message.content
                    st.success("Description generated successfully!")

                except Exception as e:
                    st.error(f"Error generating description: {str(e)}")
                    st.stop()

                if description:
                    # Save to database
                    with st.spinner("Saving to database..."):
                        try:
                            with conn.session as s:
                                s.execute(text('''
                                    INSERT OR REPLACE INTO brand_info (id, name, url, description, updated_at)
                                    VALUES (1, :name, :url, :description, :updated_at)
                                '''), {
                                    'name': brand_name,
                                    'url': brand_url,
                                    'description': description,
                                    'updated_at': datetime.now().isoformat()
                                })
                                s.commit()

                            st.success("Brand information saved to database!")
                            st.balloons()

                            # Small delay to ensure database write completes
                            import time
                            time.sleep(0.5)

                            # Rerun to show updated brand info
                            st.rerun()
                        except Exception as e:
                            st.error(f"Database error: {str(e)}")
                            import traceback
                            st.code(traceback.format_exc())
