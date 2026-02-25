# Personal Portfolio Website with AWS Serverless Architecture

## Overview

This project is a modern, fully responsive personal portfolio website built to showcase professional skills, projects, experience, and certifications.

Instead of deploying a traditional static site, this portfolio is architected as an **event-driven serverless application on Amazon Web Services (AWS)**. It demonstrates lifecycle automation, secure backend integration, and cloud-native design principles.

The project incorporates AWS serverless services for:

- **Dynamic “Message Me” form** using AWS Lambda + Amazon SES  
- **Automated time-bound website activation** using AWS Lambda + EventBridge Scheduler  
- **Visit notifications via Amazon SNS** (email alert when someone accesses the portfolio)

This approach showcases scalable, automated, and production-aware cloud architecture while maintaining a seamless user experience.

---

## Architecture & Control Flow

### 1️. Website Activation Flow (Event-Driven Lifecycle Automation)

**Visitor clicks "Open Website (resume link)" → StartWebsite Lambda → EventBridge Scheduler → S3 static hosting enabled + 30-minute timer set → StopWebsite Lambda triggered → S3 hosting disabled**

### Flow Description

- **StartWebsite Lambda**  
  Triggered when a visitor clicks the resume/portfolio link. It enables S3 static website hosting and creates a scheduled event.

- **EventBridge Scheduler**  
  Automatically schedules the StopWebsite Lambda to execute after 30 minutes.

- **StopWebsite Lambda**  
  Disables S3 static website hosting after the activation window expires.

- **Amazon SNS**  
  Sends a notification to the portfolio owner whenever the website is activated.

- **Outcome**  
  The website becomes available for a 30-minute session and is automatically deactivated afterward, demonstrating automated lifecycle control.

---

### 2️. Contact Form Flow

**Visitor fills form → API Gateway → Lambda → Amazon SES → Inbox**

#### Description

- Visitors do not require AWS accounts.
- Lambda processes the request securely.
- SES sends the email using a verified sender identity.
- IAM roles ensure secure inter-service communication.

This design provides a scalable and serverless backend with no persistent servers.

---

## Cost Optimization Clarification

While Amazon S3 static hosting is already highly cost-efficient, the primary objective of this architecture was to demonstrate **event-driven lifecycle automation and time-bound resource control** using serverless AWS services.

In real-world production environments involving compute-heavy services such as EC2 instances, containerized workloads (ECS/Fargate), or other continuously running infrastructure, implementing a start/stop automation pattern can significantly reduce costs by eliminating idle compute charges.

This project applies that architectural pattern in a simplified context to showcase:

- Automated resource activation and deactivation
- Event-driven scheduling using EventBridge
- Infrastructure state management via Lambda
- Cost-aware cloud design thinking

The focus is on demonstrating scalable automation principles rather than minimizing already negligible static hosting costs.

---

## Features

### Cloud & Backend Features

- Automated 30-minute website activation window
- EventBridge-based scheduling
- SNS email notification on website access
- Serverless contact form (API Gateway + Lambda + SES)
- IAM least-privilege access control
- CloudWatch logging support

### Frontend Features

- Fully responsive design
- Dark / Light theme toggle (LocalStorage)
- Typing animation for professional roles
- Scroll-based section highlighting and progress indicator
- Interactive cards and animations
- Portfolio sections:
  - About
  - Skills
  - Experience
  - Projects
  - Certifications
  - Resume
  - Video Resume
  - Education
  - Contact

---

## AWS Services Used

| Service | Purpose | Advantages |
|----------|----------|-------------|
| Amazon S3 | Static hosting for portfolio | Durable, cost-efficient object storage |
| AWS Lambda | Website activation & contact form logic | Serverless, scalable, pay-per-use compute |
| Amazon EventBridge Scheduler | Automated stop trigger | Precise lifecycle automation |
| Amazon API Gateway | Connects contact form to Lambda | Secure HTTP endpoint with CORS handling |
| Amazon SES | Sends portfolio messages | Reliable transactional email delivery |
| Amazon SNS | Sends activation notifications | Real-time email alerts |
| AWS IAM | Access control between services | Secure least-privilege implementation |
| Amazon CloudWatch | Logging & monitoring | Observability and debugging |

---

## Advantages of This Architecture

- Demonstrates event-driven automation patterns
- Eliminates need for persistent backend servers
- Fully serverless and scalable
- Secure service-to-service communication using IAM
- Automated lifecycle management
- Extendable to compute-based workloads for meaningful cost savings
- Clean separation of frontend and backend components

---

## Why This Project Matters

This project goes beyond a traditional static portfolio website. It demonstrates:

- Cloud-native architectural thinking
- Serverless backend implementation
- Infrastructure lifecycle automation
- Secure API-based integrations
- Cost-aware design principles
- Practical AWS service orchestration

It reflects applied knowledge of designing scalable, automated, and production-conscious systems using AWS.
