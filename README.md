# BFE Chatbot Joule Verne :zap:

<details>
<summary>Table of Contents</summary>
   
1. [Joule Verne Overview](#project-overview)  
2. [Features](#features)  
3. [Cloud Architecture](#cloud-architecture)
   - [AWS Infrastructure](#aws-infrastructure)  
   - [Components](#components-overview)
   - [Request Flow](#request-flow)
   - [Security Groups]()  
5. [Setup and Deployment](#setup-and-deployment)  
   - [Prerequisites](#prerequisites)  
   - [Infrastructure](#infrastructure)  
   - [Deployment Steps](#deployment-steps)  
6. [Configuration](#configuration)  
   - [Environment Variables](#environment-variables)  
   - [Secrets / Credentials](#secrets--credentials)  
   - [Custom Domain & SSL Certificates](#custom-domain--ssl-certificates)  
7. [Authentication & Authorization](#authentication--authorization)  
8. [Usage](#usage)  
9. [Security Considerations](#security-considerations)  
10. [Troubleshooting](#troubleshooting)  
11. [Contributing](#contributing)  
12. [License](#license)  
13. [References](#references)
    
</details>

## Joule Verne Overview
### Presentation
![Watch the demo](docs/bfe-chatbot-demo-ezgif.com-speed.gif)
Joule Verne is a chatbot that was designed with the aim of answering requests received by the Swiss Federal Office of Energy (SFOE), ranging from the general public to parliamentaries. It was built solely using public data, that can be found on the [Publication database](https://www.bfe.admin.ch/bfe/en/home/news-und-medien/publikationen.exturl.html/aHR0cHM6Ly9wdWJkYi5iZmUuYWRtaW4uY2gvZW4vc3VjaGU=.html?keywords=&q=&from=20.10.2025&to=24.10.2025&nr=), as well as the official [website](https://www.bfe.admin.ch/bfe/en/home.html) of the SFOE.

Retrieval Augmented Generation (RAG) was the technique used to design the chatbot.
If you have an account, you can check the chatbot by yourself at https://www.joule-verne.ch

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

---

### Request Flow

1. User request hits **CloudFront + WAF** for caching and security.
2. Request forwarded to the **Application Load Balancer** (ALB) in the public subnet.
3. If the ALB recognizes the JWT tokens, it goes to step 5 directly
4. The ALB redirects the user to **Cognito** frontpage, where the user must authenticate
5. The ALB routes traffic to ECS tasks running in private subnets through a target group
6. ECS containers listen on port **8501** and process the request
7. Containers interact with **S3**, **Bedrock**, and other AWS services via **VPC endpoints**
8. Logs and metrics are sent to **CloudWatch**

---

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

---
