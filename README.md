# BFE Chatbot Joule Verne :zap:

<details>
<summary>Table of Contents</summary>
   
1. [Joule Verne Overview](#joule-verne-overview)
   - [Presentation](#presentation)
   - [Features](#features)
   - [Usage](#usage)
2. [Agentic AI](#agentic-ai)
   - [Retrieval-Augmented Generation](#retrieval-augmented-generation)
   - [Bedrock Implementation](#bedrock-implementation)
3. [Cloud Architecture](#cloud-architecture)
   - [AWS Infrastructure](#aws-infrastructure)  
   - [Components](#components-overview)
   - [Request Flow](#request-flow)
   - [Security Groups](#security-groups)
   - [CI/CD Pipeline](#cicd-pipeline)
4. [How to Install & Run Project](#how-to-install--run-project)
   - [Folder Structure](#folder-structure)
   - [Environment & Local Run](#environment--local-run)
   - [Environment Variables](#environment-variables)    
5. [References](#references)
    
</details>

## Joule Verne Overview
### Presentation
![Watch the demo](docs/bfe-chatbot-demo-ezgif.com-speed.gif)
Joule Verne is a chatbot that was designed with the aim of answering requests received by the Swiss Federal Office of Energy (SFOE), ranging from the general public to parliamentarians. It was built solely using public data, that can be found on the [Publication database](https://www.bfe.admin.ch/bfe/en/home/news-und-medien/publikationen.exturl.html/aHR0cHM6Ly9wdWJkYi5iZmUuYWRtaW4uY2gvZW4vc3VjaGU=.html?keywords=&q=&from=20.10.2025&to=24.10.2025&nr=), the official [website](https://www.bfe.admin.ch/bfe/en/home.html) of the SFOE, [EnergieSchweiz](https://www.energieschweiz.ch/), [Aramis](https://www.aramis.admin.ch/) research project publications, and [Fedlex](https://www.fedlex.admin.ch/) legal texts. The main purpose of this agent is to support the Bundes-und Parlamentsgeschäfte Section to answer all letters addressed to the SFOE. Sources are shown with each answer and can be downloaded for consultation.

### Features

- **Document upload** — Upload up to 5 documents (PDF, TXT, DOCX, XLSX, CSV, max 10 MB each) to ask questions about them during the session. Large text documents are automatically summarized; large tabular files (XLSX, CSV) are routed to Code Interpreter for analysis.
- **Web search mode** — Switch between the internal BFE knowledge base and an external web search agent. The mode is locked once a conversation starts.
- **Source display** — The sidebar shows all cited sources: PDF downloads, website links, and Fedlex law references.
- **Feedback system** — Rate answers with thumbs up/down and leave optional text comments. Feedback is stored in S3 for evaluation.
- **Reasoning trace** — Expand the "Denkprozess" section to see the agent's reasoning steps, knowledge base lookups, and action group calls.
- **Interrupted query recovery** — If processing is interrupted (e.g., by a page interaction), the app detects it and offers a retry button.
- **Release notes** — Available via the sidebar footer link, automatically fetched from GitHub releases at build time.
- **Group-based authorization** — Access is restricted via Cognito groups (`ALLOWED_COGNITO_GROUPS`).

### Usage

If you have an account, you can check the chatbot at https://www.joule-verne.ch.
More information on how to use the agent and the data it relies on can be found [here](docs/chatbot-instructions.docx).

> [!CAUTION]
> When using the app, the user should always be very careful not to prompt any private data, and check the sources when unsure.


## Agentic AI
### Retrieval-Augmented Generation (RAG)
The technique used to design the agent is called Retrieval-Augmented Generation. The idea is to upload the data we want our agent to know into a vector database. For this, they will be chunked and vectorized, that is, embedded in a mathematical form. When a user makes a query to the chatbot, the query will be compared to the vector database and a semantic search will be performed, retrieving the most similar documents from the database. These documents are then added to the user's question in the prompt and the LLM will reply according to this combined prompt and context. For more details please consult the [References](#references) section.


### Bedrock Implementation
The agent is hosted on Amazon Bedrock and uses **Claude Sonnet 4.6** as LLM (configured in the infrastructure repo, not here). Two agents are configured:
- **Default agent** (`AGENT_ID` / `AGENT_ALIAS_ID`) — uses the internal knowledge bases
- **Web search agent** (`AGENT_SEARCH_ID` / `AGENT_SEARCH_ALIAS_ID`) — extends retrieval with external web search

Four knowledge base buckets are used:
| Bucket env var | Content |
|---|---|
| `PDF_BUCKET` | Public PDF documents from the Publications Database and Aramis research projects |
| `EXTRACTED_BUCKET` | Extracted text versions of PDFs (chunked with `_partN.txt` naming) |
| `WEBSITE_BUCKET` | Scraped content from the official BFE website and EnergieSchweiz |
| `FEDLEX_BUCKET` | Swiss federal law texts from Fedlex |

Three knowledge bases are configured: two use semantic chunking (documents and website) and one uses hierarchical chunking (Fedlex). The vector store is Amazon S3.

## Cloud Architecture
### AWS Infrastructure
<img width="1600" height="900" alt="image" src="https://github.com/user-attachments/assets/e58f5881-1750-4406-9015-31d50055ad4c" />


### Components Overview

- **CloudFront + WAF**
  CloudFront acts as a CDN for caching and low latency and WAF protects against common web attacks

- **Virtual Private Cloud (VPC)**
  Provides network isolation with private and public subnets across two Availability Zones (AZs)
> [!NOTE]
> Deployment spans two AZs for ensuring high availability.

- **Load Balancer (ALB)**  
  - Located in public subnets, distributes incoming traffic to ECS tasks
  - Present in both AZs for high availability
  - Associated Security Group: allows inbound traffic on port 443 from CloudFront
    
> [!TIP]
> Another option for the ALB would be to put it in a private subnet for enhanced security. If doing this, a NAT Gateway should also be added so that it can communicate through a secure internet connexion the tokens to Cognito. It was decided to opt for this public option as it is still safe and including a NAT Gateway is more expensive.

- **Elastic Container Service (ECS) using Fargate**
  - Runs Docker containers inside private subnets for security
  - Containers listen on port **8501**
  - ECS Service is deployed across both AZs for fault tolerance
  - Associated Security Group: allows inbound traffic on port 8501 from the Load Balancer Security Group
    
> [!NOTE]
> ECS uses **Fargate**, so no management of underlying instances is required as it is serverless.


- **VPC Endpoints**  
  - Enable private, secure access to AWS services without internet traffic (also less expensive than using a NAT Gateway), including:  
    - S3 for retrieving the files stored in S3
    - Bedrock for API calls to the agent
    - ECR for calling the Docker image 
    - CloudWatch for logging and monitoring
      
> [!NOTE]
> The Endpoint type of S3 is Gateway, so instead of being only attached to the corresponding subnets and security groups, the routing table of the private subnets must be modified to include the endpoint.

- **AWS Cognito**  
  Handles user authentication and authorization through a User Pool. Access is restricted to specific Cognito groups defined in the `ALLOWED_COGNITO_GROUPS` environment variable.

- **CloudWatch**
  Aggregates logs and metrics from ECS for observability


### Request Flow

1. User request hits **CloudFront + WAF** for caching and security.
2. Request forwarded to the **Application Load Balancer** (ALB) in the public subnet.
3. If the ALB recognizes the JWT tokens, it goes to step 5 directly.
4. The ALB redirects the user to **Cognito** frontpage, where the user must authenticate.
5. The ALB routes traffic to ECS tasks running in private subnets through a target group.
6. ECS containers listen on port **8501** and process the request.
7. Containers interact with **S3**, **Bedrock**, and other AWS services via **VPC endpoints**.
8. Logs and metrics are sent to **CloudWatch**.

### Security Groups

| Load Balancer SG           | Port range/protocol                                     |        Source/Destination                       |
|-------------------------|----------------------------------------------|----------------------------------------------|
| Inbound        | HTTPS 443             | CloudFront IP range (list defined by AWS)|
| Outbound           |    HTTPS 443   | Default route 0.0.0.0/0 |
| Outbound       |   All TCP 	0 - 65535 |   ECS SG |

| Elastic Container Service SG           | Port range/protocol                                     |        Source/Destination                       |
|-------------------------|----------------------------------------------|----------------------------------------------|
| Inbound        | HTTPS 443             | ECS SG|
| Inbound       |  HTTP 8501  |  Load Balancer SG   |
| Outbound           |    All TCP   | Default route 0.0.0.0/0 |

> [!IMPORTANT]
> To allow a route 443 all the way through (in and out) is primordial to allow the JWT exchange between the ALB and Cognito.
> The VPC endpoints are contained in the ECS Security group, so opening an https inside of the ECS SG is necessary to allow traffic with the S3 Gateway Endpoint.


### CI/CD Pipeline

The repository uses GitHub Actions (`.github/workflows/upload-to-ecr.yml`) with reusable workflows from `SFOE-prometheon/github-terraform-workflows`:

| Trigger | Image tag | Target |
|---------|-----------|--------|
| Pull Request (opened/sync/reopen) | `pr-<number>` | Dev ECR |
| Push to `main` | `latest` | Dev ECR |
| GitHub Release created | `<tag_name>` | Dev + Prod ECR |

The Docker build uses a multi-stage Dockerfile (build stage with compilation tools, slim runtime stage) and fetches release notes from GitHub at build time.

## How to Install & Run Project
### Folder structure
```
.
└── BFE-Chatbot-Joule-Verne/
    ├── .github/
    │   └── workflows/
    │       └── upload-to-ecr.yml       # CI/CD: build, scan, push Docker image to ECR
    ├── .streamlit/
    │   └── config.toml                 # Streamlit theme and server settings
    ├── docs/
    │   ├── bfe-chatbot-demo-ezgif.com-speed.gif
    │   └── chatbot-instructions.docx
    ├── img/
    │   └── bundesamt_logo.jpeg         # Swiss Federal Office logo for the frontend
    ├── pages/
    │   └── release_notes.py            # Streamlit page: displays release notes
    ├── scripts/
    │   └── fetch_releases.py           # Fetches GitHub releases → release_notes.json
    ├── src/
    │   ├── __init__.py
    │   ├── document_processing.py      # Multi-document upload: extraction, summarization, chunking
    │   └── utils.py                    # AWS clients, agent invocation, S3 helpers, feedback
    ├── .dockerignore
    ├── .env                            # Local environment variables (not committed)
    ├── .gitignore
    ├── agent.py                        # Main Streamlit app: frontend + chat logic
    ├── Dockerfile                      # Multi-stage build for ECS deployment
    ├── README.md
    └── requirements.txt
```

### Environment & Local Run

```bash
python -m venv venv
source venv/bin/activate         # macOS / Linux
# venv\Scripts\activate          # Windows
pip install -r requirements.txt
streamlit run agent.py           # runs on http://localhost:8501
```

### Environment Variables

The following environment variables are required (set in `.env` locally, or in the ECS task definition for deployment):

| Variable | Description |
|----------|-------------|
| `AWS_REGION` | AWS region (e.g. `eu-central-1`) |
| `AGENT_ID` | Bedrock Agent ID (default/knowledge base agent) |
| `AGENT_ALIAS_ID` | Alias ID for the default agent |
| `AGENT_SEARCH_ID` | Bedrock Agent ID (web search agent) |
| `AGENT_SEARCH_ALIAS_ID` | Alias ID for the web search agent |
| `PDF_BUCKET` | S3 bucket containing the PDF documents |
| `EXTRACTED_BUCKET` | S3 bucket with extracted text files |
| `WEBSITE_BUCKET` | S3 bucket with scraped BFE website content |
| `FEDLEX_BUCKET` | S3 bucket with Fedlex law texts |
| `FEEDBACK_BUCKET` | S3 bucket for storing user feedback |
| `ALLOWED_COGNITO_GROUPS` | Comma-separated Cognito group names allowed to access the app |

## References
- Gao, Yunfan, et al. "Retrieval-augmented generation for large language models: A survey." arXiv preprint arXiv:2312.10997 2.1 (2023).
- [LlamaIndex Python documentation](https://developers.llamaindex.ai/python/framework/)
- [AWS Python SDK documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html)
