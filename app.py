import streamlit as st
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="Business Clarity Workshop - Attendance Matrix", layout="wide")

st.title("Workshop Engagement & Clustering Data Prep")

col1, col2 = st.columns(2)
with col1:
    # Enabled accept_multiple_files for batch uploads
    uploaded_files = st.file_uploader("Upload Zoom CSV(s)", type=['csv'], accept_multiple_files=True)
with col2:
    # Removed the static Date input; time applies universally across all uploaded workshop days
    official_start_time = st.time_input("Official Start Time (Applies to all files)", value=pd.to_datetime("10:30").time())

if uploaded_files: # Check if the list is not empty
    try:
        all_data = []
        
        for uploaded_file in uploaded_files:
            df = pd.read_csv(uploaded_file)
            
            # Convert Join and Leave times to datetime objects
            df['Join Time'] = pd.to_datetime(df['Join Time'])
            df['Leave Time'] = pd.to_datetime(df['Leave Time'])
            
            # Calculate active duration for each individual session/row in minutes
            df['Session Duration Mins'] = (df['Leave Time'] - df['Join Time']).dt.total_seconds() / 60
            
            # Aggregate by participant (including email for uniqueness)
            summary = df.groupby(['User Name', 'User Email']).agg(
                first_join=('Join Time', 'min'),
                last_leave=('Leave Time', 'max'),
                actual_duration_mins=('Session Duration Mins', 'sum')
            ).reset_index()
            
            # 1. Add Workshop Date extracted from their first join time
            summary['Workshop Date'] = summary['first_join'].dt.date
            
            # Calculate Total Span (Duration 1)
            summary['total_span_mins'] = (summary['last_leave'] - summary['first_join']).dt.total_seconds() / 60
            
            # Calculate Time Away (Drop-offs / breaks)
            summary['time_away_mins'] = summary['total_span_mins'] - summary['actual_duration_mins']
            summary['time_away_mins'] = summary['time_away_mins'].round(2).clip(lower=0)
            
            # 2. Dynamic Punctuality Matrix (Combines their specific Workshop Date with the Official Start Time)
            def get_official_start(date_val):
                return pd.to_datetime(f"{date_val} {official_start_time}")
                
            summary['official_start_dt'] = summary['Workshop Date'].apply(get_official_start)
            
            summary['minutes_late'] = (summary['first_join'] - summary['official_start_dt']).dt.total_seconds() / 60
            summary['minutes_late'] = summary['minutes_late'].round(2)
            
            # Categorical labels
            def categorize_arrival(mins):
                if mins < -5: return "Early"
                elif mins <= 5: return "On Time"
                else: return "Late"
                
            summary['arrival_category'] = summary['minutes_late'].apply(categorize_arrival)
            
            # Drop the temporary datetime column before appending
            summary = summary.drop(columns=['official_start_dt'])
            
            all_data.append(summary)
            
        # Combine all processed files into a single DataFrame
        final_matrix = pd.concat(all_data, ignore_index=True)
        
        # Reorder columns to put Workshop Date upfront
        cols = final_matrix.columns.tolist()
        cols.insert(2, cols.pop(cols.index('Workshop Date')))
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
        
    except Exception as e:
        st.error(f"Error processing files. Details: {e}")
