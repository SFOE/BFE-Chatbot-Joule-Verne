# BFE Chatbot Joule Verne :zap:

<details>
<summary>Table of Contents</summary>
   
1. [Joule Verne Overview](#joule-verne-overview)
   - [Presentation](#presentation)
   - [Usage](#usage)
   - [What's next?](#whats-next)
3. [Agent Features](#agent-features)  
4. [Cloud Architecture](#cloud-architecture)
   - [AWS Infrastructure](#aws-infrastructure)  
   - [Components](#components-overview)
   - [Request Flow](#request-flow)
   - [Security Groups](#security-groups)
   - [Deployement Flow](#deployment-flow)
5. [How to Install & Run Project for Data Updates](#how-to-install--run-project)
   - [Folder Structure](#folder-structure)
   - [Environment & Local Run](#environment--local-run)
   - [Updating Data](#updating-data)
   - [Environment Variables](#environment-variables)  
8. [Authentication & Authorization](#authentication--authorization)   
9. [Security Considerations](#security-considerations)
12. [License](#license)  
13. [References](#references)
    
</details>

## Joule Verne Overview
### Presentation
![Watch the demo](docs/bfe-chatbot-demo-ezgif.com-speed.gif)
Joule Verne is a chatbot that was designed with the aim of answering requests received by the Swiss Federal Office of Energy (SFOE), ranging from the general public to parliamentaries. It was built solely using public data, that can be found on the [Publication database](https://www.bfe.admin.ch/bfe/en/home/news-und-medien/publikationen.exturl.html/aHR0cHM6Ly9wdWJkYi5iZmUuYWRtaW4uY2gvZW4vc3VjaGU=.html?keywords=&q=&from=20.10.2025&to=24.10.2025&nr=), as well as the official [website](https://www.bfe.admin.ch/bfe/en/home.html) of the SFOE. The main purpose of this agent is to support the Bundes-und Parliamentsgeschäfte Section to answer all letters addressed to the SFOE. Sources are explicited with each answers and can be downloaded for consultation.


### Usage

If you have an account, you can check the chatbot by yourself at https://www.joule-verne.ch.
More information useful to the user on how to use the agent and the used data can be found [here](docs/chatbot-instructions.docx?raw=1).


### What's next?

As of today (November 2025), only the documents in pdf format have been added to the workflow. For future use, we could consider adding more datatypes (such as Excel for instance) and automatically upload the data to the Vector knowledge base stored on AWS, after agreement over the update frequency and whether older data should be deleted, in order to keep the costs low and the information provided to the chatbot up-to-date. We will also integrate the authentication system with the Smartcard, so that access can be extended to all people working at the SFOE and as well as at other offices. In the long term, another version of the chatbot might be made public.

## Agent Features
### Retrieval Augmented Generation (RAG)
The technique used to design the agent is called Retrieval Augmented Generation. The idea is to upload the data we want our agent to know of in a vector database. For this, they will be chunked off and vectorized, that is to say embedded in a mathematical form. When a user will make a query to the chatbot, the query will be compared to the vector database and a semantic search will be performed, retrieving the most similar documents from the database. These documents will then be added to the user's question in the prompt and the LLM will reply according to this new prompt and context. For more details refer to the 
> [!NOTE]
> Useful information that users should know, even when skimming content.

### Bedrock Implementation
The LLM leveraged by the agent is Claude Sonnet 3.5. The agent is hosted on Bedrock and called `BFE-agent`. Two knowledge bases are provided, one containing the data of the official BFE website `bfe-website-knowledge-base`, the other containing the public pdf documents of the Publications Database `knowledge-base-documents-s3`. Both knowledge bases use semantic chunking, basic parsing and a token size of 512. The pdf documents are 1000 in total and contained between the 29th of August 2022 and the 24th of October 2025, and for 500 of them advanced parsing was performed using the LLM parser from LlamaIndex. This solution could nonetheless not be implemented for the whole dataset, as only a handful of documents can be treated this way using free-tier, and no entreprise account was deemed necessary to open at the time. The vector store used was Amazon OpenSearch Service's vector database for both knowledge bases. In the future one might consider to use the S3 native vector store, which is still in its beta version today and recommended against for production at the time.

## Cloud Architecture
### AWS Infrastructure
The architecture was deployed with the AWS infrastructure.
<img width="1600" height="900" alt="image" src="https://github.com/user-attachments/assets/e58f5881-1750-4406-9015-31d50055ad4c" />


### Components Overview

- **CloudFront + WAF**
  CloudFront acts as a CDN for caching and low latency and WAF protects against common web attacks

- **Virtual Private Cloud (VPC)**
  Provides network isolation with private and public subnets across two Availability Zones (AZs)
  
  > ℹ️ Deployment spans two AZs for ensuring high availability.

- **Load Balancer (ALB)**  
  - Located in public subnets, distributes incoming traffic to ECS tasks [^2]
  - Present in both AZs for high availability
  - Associated Security Group: allows inbound traffic on port 443 from CloudFront
    
   > ℹ️ Another option for the ALB would be to put it in a private subnet for enhanced security. If doing this, a NAT Gateway should also be added so that it can communicate through a secure internet connexion the tokens to Cognito. It was decided to opt for this public option as it is still safe and including a NAT Gateway is more expensive

- **Elastic Container Service (ECS) using Fargate**[^3] 
  - Runs Docker containers inside private subnets for security
  - Containers listen on port **8501**
  - ECS Service is deployed across both AZs for fault tolerance
  - Associated Security Group: allows inbound traffic on port 8501 from the Load Balancer Security Group
    
   > ℹ️ ECS uses **Fargate**, so no management of underlying instances is required as it is serverless.


- **VPC Endpoints**  
  - Enable private, secure access to AWS services without internet traffic (also less expensive than using a NAT Gateway), including:  
    - S3 for retrieving the files stored in S3
    - Bedrock for API calls to the agent
    - ECR for calling the Docker image 
    - CloudWatch for logging and monitoring
      
   > ℹ️ The Endpoint type of S3 is Gateway, so instead of being only attached to the corresponding subnets and security groups, the routing table of the (private in this case) subnets must be modified to include the endpoint.

- **AWS Cognito**  
  Handles user authentication and authorization through a User pool (as the access is restrained right now we can add the users manually)

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

> ℹ️ To allow a route 443 all the way through (in and out) is primordial to allow the JWT exchange between the ALB and Cognito.
>  The VPC endpoints are contained in the ECS Security group, so opening an https inside of the ECS SG is necessary to allow traffic with the S3 Gateway Endpoint.



### Deployment Flow

1. The Docker image of the app is uploaded on the **Elastic Container Registry** (ECR).
2. A task is created on ECS that chooses the image to use and takes the environment variables and the exposed port as parameters.
3. A service is created on ECS that specify the task that will run and that Fargate will be used.
4. Fargate provides the computing ressources and the containers defined on the service are launched.
5. Because an ALB is used, the service automatically registers the IPs/ports of the launched task in the target group so that the ALB can route traffic to the app.

## How to Install & Run Project for Data Updates
### Folder structure
```
.
└── AWS-AgenticAI/
    ├── streamlit/
    │   └── config.toml 
    ├── data/
    │   └── metadata.jsonl
    ├── docs
    ├── img
    ├── src/
    │   ├── archive/
    │   │   └── batch_loading.py 
    │   ├── __init__.py
    │   ├── upload_data_to_s3.py 
    │   ├── utils.py
    │   └── webscraping.py 
    ├── .dockerignore
    ├── .env
    ├── .gitignore
    ├── agent.py 
    ├── Dockerfile
    ├── README.md
    └── requirements.txt
```
`streamlit/config.toml` : custom settings for the frontend

`data/metadata.jsonl` : the metadata downloaded from the publishing website, ready to be uploaded to S3
     
`docs/` : the docs needed to produce the README
     
`img/` : the Swiss vignette for the frontend

`src/` :
   - `archive/batch_loading.py` : used to parse data with LlamaParse, not free if CI/CD implemented (restricted free usage)
   - `webscraping.py` : scrape publishing website and adds most recent pdfs from a certain date DATE to the metadata.jsonl
   - `upload_data_to_s3.py` :  upload data with their metadata to S3 under bfe-public-data-pdf/pdfs-batch/. Use Athena queries to filter what data to upload
     
`agent.py` : the streamlit script containing the frontend design


### Environment & Local Run

In order to create an environment, install the required dependencies and run the app locally you can use the following commands:
```bash
python -m venv venv #create the environment
# Activate the environment
source venv/bin/activate         # macOS / Linux
venv\Scripts\activate            # Windows
pip install -r requirements.txt #install dependencies
streamlit run agent.py # run the app locally on port 8501
```

### Updating Data

If there is a need to update the data from the Publishing website manually, you can follow the following steps:

1. Create the environment as explained above.
2. Run script `webscraping.py` with the parameter DATE updated. The metadata.jsonl will then be updated with all pdf published between DATE and now.
3. Modify the QUERY in `upload_data_to_S3.py` at your convenience to filter the data. If the filtered files are not already present in S3, they will be uploaded.
4. Sync an existing data source that points to the correct S3 bucket in the `knowledge-base-documents-s3` Knowledge base in Bedrock.
5. Now you are all set ! 🎉


### Environment Variables

The environment variables can be found under the task definition `chatbot-server-task` and `Environment and secrets` of the SFOE AWS Data Science account.

## Security Considerations
When using the app, the user should always be very careful not to prompt with any private data, and check the sources when unsure.

## References
- Gao, Yunfan, et al. "Retrieval-augmented generation for large language models: A survey." arXiv preprint arXiv:2312.10997 2.1 (2023).
- [LlamaIndex Python documentation](https://developers.llamaindex.ai/python/framework/)
- [AWS Python SDK documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html)
