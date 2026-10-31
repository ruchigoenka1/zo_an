import streamlit as st
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="Business Clarity Workshop - Attendance Matrix", layout="wide")

st.title("Workshop Engagement & Clustering Data Prep")

col1, col2 = st.columns(2)
with col1:
    uploaded_files = st.file_uploader("Upload Zoom Data", type=['csv', 'xlsx'], accept_multiple_files=True)
with col2:
    official_start_time = st.time_input("Official Start Time (Applies to all files)", value=pd.to_datetime("10:30").time())

def align_headers(df):
    """Scans the first 15 rows to find the actual Zoom headers if metadata is at the top."""
    # Check if current columns already look correct
    cols_str = df.columns.astype(str).str.lower()
    if any('join' in c for c in cols_str) and any('time' in c for c in cols_str):
        return df
    
    # If not, scan the first few rows for the 'Join Time' string
    for i, row in df.head(15).iterrows():
        row_str = row.astype(str).str.lower()
        if any('join' in val and 'time' in val for val in row_str):
            df.columns = row.tolist() # Set the found row as headers
            return df.iloc[i+1:].reset_index(drop=True) # Return data below the header
            
    return df

if uploaded_files:
    try:
        all_data = []
        
        for uploaded_file in uploaded_files:
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            elif uploaded_file.name.endswith('.xlsx'):
                df = pd.read_excel(uploaded_file)
            else:
                continue
            
            # 1. Dynamically find the real headers
            df = align_headers(df)
            
            # 2. Standardize column names
            df.columns = df.columns.astype(str).str.strip().str.lower()
            
            # 3. Identify standard columns safely
            name_col = next((col for col in df.columns if 'name' in col), None)
            email_col = next((col for col in df.columns if 'email' in col), None)
            join_col = next((col for col in df.columns if 'join' in col and 'time' in col), None)
            leave_col = next((col for col in df.columns if 'leave' in col and 'time' in col), None)
            
            # Fallbacks
            if not join_col: join_col = next((col for col in df.columns if 'join' in col), None)
            if not leave_col: leave_col = next((col for col in df.columns if 'leave' in col), None)
            
            if not all([name_col, join_col, leave_col]):
                st.warning(f"File '{uploaded_file.name}' is missing standard Zoom columns. Skipping.")
                continue
            
            # 4. Parse datetimes (removed 'mixed' format as Excel often handles this natively)
            df[join_col] = pd.to_datetime(df[join_col], errors='coerce')
            df[leave_col] = pd.to_datetime(df[leave_col], errors='coerce')
            
            # Drop empty/summary rows
            df = df.dropna(subset=[join_col, leave_col])
            
            if df.empty:
                continue
                
            # Calculate metrics
            df['Session Duration Mins'] = (df[leave_col] - df[join_col]).dt.total_seconds() / 60
            
            group_cols = [name_col, email_col] if email_col else [name_col]
            
            summary = df.groupby(group_cols).agg(
                first_join=(join_col, 'min'),
                last_leave=(leave_col, 'max'),
                actual_duration_mins=('Session Duration Mins', 'sum')
            ).reset_index()
            
            # Restore display names
            summary.rename(columns={name_col: 'User Name'}, inplace=True)
            if email_col:
                summary.rename(columns={email_col: 'User Email'}, inplace=True)
            
            summary['Workshop Date'] = summary['first_join'].dt.date
            summary['total_span_mins'] = (summary['last_leave'] - summary['first_join']).dt.total_seconds() / 60
            summary['time_away_mins'] = (summary['total_span_mins'] - summary['actual_duration_mins']).round(2).clip(lower=0)
            
            date_str = summary['Workshop Date'].astype(str)
            time_str = official_start_time.strftime("%H:%M:%S")
            summary['official_start_dt'] = pd.to_datetime(date_str + " " + time_str)
            
            summary['minutes_late'] = (summary['first_join'] - summary['official_start_dt']).dt.total_seconds() / 60
            summary['minutes_late'] = summary['minutes_late'].round(2)
            
            def categorize_arrival(mins):
                if mins < -5: return "Early"
                elif mins <= 5: return "On Time"
                else: return "Late"
                
            summary['arrival_category'] = summary['minutes_late'].apply(categorize_arrival)
            summary = summary.drop(columns=['official_start_dt'])
            all_data.append(summary)
            
        if all_data:
            final_matrix = pd.concat(all_data, ignore_index=True)
            
            cols = final_matrix.columns.tolist()
            if 'Workshop Date' in cols:
                insert_idx = 2 if 'User Email' in cols else 1
                cols.insert(insert_idx, cols.pop(cols.index('Workshop Date')))
                final_matrix = final_matrix[cols]
            
            st.subheader("Processed Participant Matrix")
            st.dataframe(final_matrix, use_container_width=True)
            
            csv_export = final_matrix.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Download Master Data for Clustering",
                data=csv_export,
                file_name="master_workshop_clustering_matrix.csv",
                mime="text/csv",
            )
        else:
            st.warning("No valid datetime data found. Please ensure files contain actual participant join/leave times.")
            
    except Exception as e:
        st.error(f"Error processing files. Details: {e}")
