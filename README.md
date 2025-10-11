# Personal Portfolio Website with AWS Serverless Architecture

## Overview

This is a modern, fully responsive personal portfolio website built to showcase professional skills, projects, experience, and certifications. The project incorporates **serverless AWS services** for both the **contact form** and **cost-optimized temporary website hosting**:

- **Dynamic “Message Me” form** using AWS Lambda + SES  
- **Temporary website activation** using AWS Lambda + EventBridge Scheduler, limiting hosting to **30 minutes per session** for cost optimization  

This approach demonstrates **scalable, cost-efficient cloud design** while providing a professional portfolio experience.

---

## Architecture & Control Flow

### Website Activation Flow (Cost Optimization)

**Visitor clicks "Open Website (resume link)"
    |
StartWebsite Lambda
    |
EventBridge Scheduler triggers
    |
Activates S3 static website hosting & sets 30-minute timer
    |
StopWebsite Lambda triggered
    |
S3 Website is disabled until next request**



### Description:
- **StartWebsite Lambda:** Triggered when someone clicks the resume/portfolio link.
- **EventBridge Scheduler:** Automatically schedules StopWebsite Lambda 30 minutes later.
- **StopWebsite Lambda:** Disables the S3 static website hosting to reduce costs.
- **Outcome:** Website is only active for 30 minutes per visitor/session, minimizing S3 costs.

### Contact Form Flow

**Visitor fills form → API Gateway → Lambda → Amazon SES → Your Inbox**

- Visitors do not need AWS accounts or verified emails
- Lambda sends email using verified FROM email/domain
- SES delivers messages to your inbox

### Features
- Temporary Portfolio Website Hosting (30 min)
- Only activates when a visitor clicks the link from your resume
- Automatically disables after 30 minutes
- Reduces hosting costs without affecting user experience
- Dynamic Contact Form
- Sends emails via AWS Lambda + SES
- Visitors’ emails are included in the message body; no verification required
- Modern UI Features
- Dark/Light theme toggle with LocalStorage
- Typing animation for professional roles
- Scroll-based section highlighting and progress bar
- Interactive cards and intersection-based animations
- Portfolio Sections: About, Skills, Experience, Projects, Certifications, Resume, Video Resume, Education, Contact

### AWS Services Used
| Service                | Purpose                             | Advantages                                           |
|------------------------|-------------------------------------|----------------------------------------------------|
| S3                     | Static hosting for portfolio        | Cost-efficient, globally available, highly durable|
| Lambda                 | Contact form logic & website activation | Serverless, scalable, pay-per-use                 |
| EventBridge Scheduler  | Schedule automatic stop of website  | Automation, precise timing, cost-saving           |
| API Gateway            | Connects website form to Lambda     | Secure HTTP endpoint, handles CORS                |
| SES                    | Sends portfolio messages            | Reliable email delivery, verified sender ensures authenticity |


### Advantages
- Cost Optimization: Website runs only 30 minutes per session.
- Serverless & Scalable: Lambda and EventBridge manage all backend logic without servers.
- Visitor-Friendly: Anyone can submit contact form; no AWS account needed.
- Reliable & Secure: SES verified domain ensures email delivery; IAM roles control access.
- Maintainable: Modular serverless architecture allows easy extension or updates.
