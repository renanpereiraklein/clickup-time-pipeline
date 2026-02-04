# ClickUp Time Tracking Data Pipeline

A Python-based data ingestion pipeline designed to extract, reconstruct, and normalize historical time tracking data from ClickUp’s API for reliable workforce analytics.

This project focuses on overcoming API limitations, user-scoped query constraints, and data loss caused by deleted accounts.

---

## Problem

ClickUp’s time tracking API requires user-based parameters (`assignee`) for querying time entries and limits responses to 100 records per request.

When employees leave and their accounts are deleted, historical work data becomes inaccessible through standard API queries. This leads to incomplete datasets and misleading productivity reports.

---

## Solution

This pipeline implements a robust extraction strategy that:

- Crawls all tasks (including closed tasks and subtasks) to discover historical users  
- Reconstructs deleted and inactive user references  
- Queries time entries dynamically per user  
- Uses adaptive time-window bisection with overlap to bypass record limits  
- Deduplicates overlapping results by entry ID  
- Produces normalized outputs for BI and analytics systems  

---

## Architecture

ClickUp API
↓
Task Crawler (User Discovery)
↓
Time Entry Extractor (User-Scoped Queries)
↓
Adaptive Window Splitter (Bisection + Overlap)
↓
Deduplication Layer
↓
Normalized JSON Output

---

## Tech Stack

- Python
- ClickUp REST API
- ETL / Data Engineering
- Data Normalization
- Automation Pipelines

---

## Setup

### 1. Environment Variables

Set the following environment variables:

CLICKUP_API_TOKEN=your_api_token
TEAM_ID=your_team_id

Example (Linux / macOS):

```bash
export CLICKUP_API_TOKEN="your_token"
export TEAM_ID="your_team_id"
```
Windows (PowerShell):
```setx CLICKUP_API_TOKEN "your_token"
setx TEAM_ID "your_team_id"
```

Install Dependencies
pip install requests
