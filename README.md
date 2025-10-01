# AWS Architecture Summary

<img width="1600" height="900" alt="image" src="https://github.com/user-attachments/assets/e58f5881-1750-4406-9015-31d50055ad4c" />


## Components Overview

- **CloudFront + WAF**
  CloudFront acts as a CDN for caching and low latency and WAF protects against common web attacks

- **Virtual Private Cloud (VPC)**
  Provides network isolation with private and public subnets across two Availability Zones (AZs) [^1]

- **Load Balancer (ALB)**  
  - Located in public subnets, distributes incoming traffic to ECS tasks [^2]
  - Present in both AZs for high availability
  - Associated Security Group: allows inbound traffic on port 80/443 from CloudFront
    [^2]: Another option for the ALB would be to put it in a private subnet for enhanced security. If doing this, a NAT Gateway should also be added so that it can communicate through a secure internet connexion the tokens to Cognito. It was decided to opt for this public option as it is still safe and including a NAT Gateway is more expensive

- **Elastic Container Service (ECS) using Fargate**[^3] 
  - Runs Docker containers inside private subnets for security
  - Containers listen on port **8501**
  - ECS Service is deployed across both AZs for fault tolerance
  - Associated Security Group: allows inbound traffic on port 8501 from the Load Balancer Security Group

- **VPC Endpoints**  
  - Enable private, secure access to AWS services without internet traffic (also less expensive than using a NAT Gateway), including:  
    - S3 for retrieving the files stored in S3 [^5]
      [^5]: The Endpoint type of S3 is Gateway, so instead of being only attached to the corresponding subnets and security groups, the routing table of the (private in this case) subnets must be modified to include the endpoint.
    - Bedrock for API calls to the agent
    - ECR for calling the Docker image 
    - CloudWatch for logging and monitoring

- **AWS Cognito**  
  Handles user authentication and authorization through a User pool (as the access is restrained right now we can add the users manually)

- **CloudWatch**
  Aggregates logs and metrics from ECS for observability

---

## Request Flow

1. User request hits **CloudFront + WAF** for caching and security.
2. Request forwarded to the **Application Load Balancer** (ALB) in the public subnet.
3. If the ALB recognizes the JWT tokens, it goes to step 5 directly
4. The ALB redirects the user to **Cognito** frontpage, where the user must authenticate
5. The ALB routes traffic to ECS tasks running in private subnets through a target group
6. ECS containers listen on port **8501** and process the request
7. Containers interact with **S3**, **Bedrock**, and other AWS services via **VPC endpoints**
8. Logs and metrics are sent to **CloudWatch**

---

## Security Groups Summary

| Security Group           | Purpose                                      | Rules Summary                                |
|-------------------------|----------------------------------------------|----------------------------------------------|
| Load Balancer SG         | Controls inbound traffic to ALB               | Inbound: Allow HTTP/HTTPS from CloudFront IPs |
| ECS Service SG           | Controls inbound traffic to ECS tasks[^4]        | Inbound: Allow traffic on port 8501 from Load Balancer SG |

---

[^3]: ECS uses **Fargate**, so no management of underlying instances is required.
[^1]: Deployment spans **two Availability Zones** for high availability.
[^4]: The VPC endpoints are contained in the ECS Security group.
