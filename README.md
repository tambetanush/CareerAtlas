# CareerAtlas

**Note: The working repository is currently private due to workshop rules.**

## About The Project

CareerAtlas is an AI-powered platform designed to supercharge your career journey. It acts as an intelligent career companion, analyzing your resume, identifying skills gaps, researching the market, and matching you with relevant job opportunities.

Through its multi-agent architecture, CareerAtlas provides tailored roadmaps and actionable insights to help you achieve your career goals.

## Features

- **Intelligent Resume Extraction:** Automatically parses resumes to extract key skills, work experience, and personal projects.
- **Skill Gap Analysis:** Compares your current skill set against target job roles to identify missing technical and soft skills.
- **Personalized Career Roadmaps:** Generates structured learning paths to help you bridge your skill gaps and reach your career objectives.
- **Market-Driven Job Finder:** Recommends relevant job openings tailored to your profile and location.
- **Deep Research Insights:** Conducts in-depth research on industries, companies, and roles to provide actionable career intelligence.
- **Interactive Dashboard:** A seamless, user-friendly interface to track your progress, view job matches, and explore learning roadmaps.

## Methodology

CareerAtlas is built upon a **Multi-Agent Architecture** where specialized AI agents handle specific aspects of the career planning process:

1. **Extraction & Matching Agents:** Dedicated agents analyze resume data and query job markets to find the best possible matches.
2. **Gap Analysis & Research Agents:** Deep researcher agents investigate market trends, while gap analysis agents compare user profiles against industry standards.
3. **Evaluation Framework:** Extensive evaluation notebooks were developed to iteratively test, benchmark, and improve agent accuracy and reliability.
4. **Web Deployment:** The agents are orchestrated and deployed behind a visually engaging web interface, providing real-time career guidance.

## Walkthrough

Here is a visual walkthrough of the platform:

### 1. Landing Page

![Landing Page](static/1%20landing%20page.png)

### 2. User Dashboard

![Dashboard](static/2%20dashboard.png)

### 3. Resume Extraction - Skills

![Resume Skills](static/3%20resume%20skills.png)

### 4. Resume Extraction - Experience

![Resume Skills & Experience](static/4%20resume%20skills%20experience.png)

### 5. Resume Extraction - Projects

![Resume Projects](static/5%20resume%20projects.png)

### 6. Career Roadmap

![Roadmap](static/6roadmap.png)

### 7. Skill Gap Analysis

![Gap Analysis](static/7%20gaps.png)

### 8. Job Finder

![Job Finder](static/8%20jobs.png)

## Evaluation & Benchmarks

To ensure the reliability and accuracy of CareerAtlas, we developed an extensive evaluation framework using **LLM-as-a-Judge** methodologies and field-level metrics. Our evaluation process rigorous tests the core agents:

### 1. Gap Analysis Agent
We conducted a head-to-head comparison between our RAG-augmented agent (Pinecone + BM25 + Jina Reranker) and a Naive LLM across 10 realistic career transition personas. An independent LLM judge (Google Gemini) scored both approaches, proving that our agent significantly outperforms the baseline in relevance, accuracy, and actionability by grounding recommendations in real job-market taxonomy.
![Gap Analysis Evaluation](static/eval_Gap_Analysis_Evaluation_0.png)

### 2. Resume Extraction Agent
We systematically tested the extraction pipeline using ground-truth test cases, measuring field-level metrics (Precision, Recall, F1 for lists; Accuracy for strings). Real PDF resumes were also scored out of 10 by an LLM-as-Judge to guarantee high fidelity in parsing skills and experiences.
![Resume Extraction Evaluation](static/eval_resume_extraction_eval_0.png)

### 3. Deep Researcher Agent
This LangGraph-based agent (which plans, searches via Tavily, and structures learning pathways) was evaluated on diverse profiles. An OpenRouter judge validated the quality of the generated roadmaps, scoring the pathways based on resource relevance and curriculum structure.
![Deep Researcher Evaluation](static/eval_deep_researcher_evaluation_notebook_0.png)

### 4. Job Hunter Agent
Using Adzuna for search and Jina for embeddings, the job hunter was evaluated on mock profiles to ensure high role relevance, location compliance, and skill alignment.
![Job Hunter Evaluation](static/eval_job_hunter_evaluation_0.png)

## Contributors

- **Tanush Tambe** - Resume Extractor and Job Finder, Evaluation Notebooks
- **Dripto Bhattacharyya** - Deep Researcher and Deployment
- **Sidhaarth Shree** - Gap Analysis Agent
- **G Hamsini** - Contributor
- **Shivanshu Gupta** - Contributor
