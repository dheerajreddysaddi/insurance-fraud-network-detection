# AI Usage and Prompt History

**Project:** Insurance Fraud Network Detection  
**Purpose:** Disclosure of AI assistance for the YottaFlex AI candidate project.

## 1. Summary

I used AI assistants as supporting tools during development to explore technical approaches, understand unfamiliar concepts, investigate errors, review selected code, improve the application interface, and troubleshoot environment and deployment issues.

AI suggestions were treated as proposals to evaluate against the existing project, not as proof that an implementation was correct. I remain responsible for the code in this repository, the decisions made, the documentation, and any claims about test results.

## 2. Prompt history

### 2.1 Understanding the project

**Question 1 — Identify suspicious relationships**

> I am working on an insurance fraud network detection project. How can I identify relationships between claims that might be suspicious instead of checking each claim separately?

**Purpose:** Explore how relationships between claims and related entities can reveal patterns that may deserve investigation.

**Question 2 — Represent connections as a graph**

> How should I represent the connections between claims and related entities in a graph? What should be considered a node and what should be an edge?

**Purpose:** Explore a graph representation of the entities and relationships in the insurance data.

**Question 3 — Explain suspicious connections**

> I want the application to show the suspicious connections in a way that is easy to understand. What information should I display for each claim and its connected entities?

**Purpose:** Explore ways to present evidence so a reviewer can understand why a network was flagged.

### 2.2 Application and visualization

**Question 4 — Organize the Streamlit application**

> I have a Streamlit application for this project. How should I organize the pages so that users can explore the data, view the network, and investigate suspicious claims without everything appearing on one page?

**Purpose:** Explore a page structure for data exploration, network analysis, and investigation.

**Question 5 — Improve graph readability**

> The network graph is becoming difficult to read when there are too many connected nodes. How can I make the visualization easier to understand without hiding important relationships?

**Purpose:** Explore ways to improve graph readability while retaining relevant relationships.

**Question 6 — Improve dashboard consistency**

> How can I improve the layout of the Streamlit dashboard so that the metrics, tables, filters, and network visualization look consistent?

**Purpose:** Explore layout improvements for the dashboard.

### 2.3 Debugging

**Question 7 — Persistent Streamlit secrets warning**

Recorded prompts:

> what is that error on the left side

After the first attempted fix:

> the red “No secrets found” box is gone from the sidebar.-- its not gone its still there

![No secrets error](docs/images/secerts.png)

**Recorded outcome in the existing project history:** The application read `st.secrets` before the environment variable. The code was changed to read `APP_PASSCODE` from the environment first. The warning remained because the `.env` file did not exist; the recorded resolution was to create `.env` from `.env.example` and restart the application.

This is a recorded troubleshooting outcome, not a claim that every deployment configuration has been verified.

**Question 8 — Data generation appeared to stall**

Recorded command and problem:

```bash
python scripts/generate_data.py --scale full --replace 2>&1 | tail -40
```

> not giving any output even after 5 minutes

**Purpose:** Investigate a data-generation command that appeared not to produce output.

**Verification status:** The existing prompt record documents the symptom but does not record a verified final resolution. No successful completion is claimed here.

### 2.4 Testing, evaluation, deployment, and security

**Question 9 — Test application features**

> How should I test the main features of the application before deployment? I want to make sure that data loading, filtering, network visualization, and the investigation workflow work correctly.

**Purpose:** Explore testing approaches for the application's main workflows.

**Question 10 — Evaluate fraud detection**

> Which metrics should I report when evaluating a fraud detection model, and how should I explain false positives and false negatives?

**Purpose:** Understand how to communicate detection performance and the trade-offs involved in false positives and false negatives.

**Question 11 — Check for data leakage**

> How can I check for data leakage and make sure that the evaluation results represent how the model might perform on unseen data?

**Purpose:** Explore checks for leakage and evaluation design.

**Question 12 — Troubleshoot deployment**

> The application works locally, but I am having trouble deploying it to Streamlit Community Cloud. How should I check the repository configuration, dependency file, entry-point script, and secrets?

**Purpose:** Identify configuration areas to investigate when deployment differs from local execution.

**Question 13 — Protect credentials**

> How can I make sure that database credentials and other secrets are not committed to GitHub and are configured correctly in the deployment environment?

**Purpose:** Review secret handling and deployment configuration.

## 3. Project-level implementation prompt

The development materials also included a project master prompt requesting an end-to-end Insurance Fraud Detection and Network Investigation System. Its stated goals included:

- Synthetic data generation and a relational data model.
- Transparent fraud rules, evidence records, and explainable risk scoring.
- Relationship graph analysis.
- Investigation workflow and audit events.
- Evaluation metrics and data validation.
- Automated tests and reproducibility checks.
- Application and submission documentation.

The master prompt explicitly required that test results not be fabricated and that features which could not be implemented or tested be documented as limitations.

This prompt describes requested scope; it does not prove that every requested feature was implemented or passed testing.

## 4. Where AI helped

Based on the recorded prompts, AI assistance was sought for:

| Area | Intended assistance | Evidence needed to confirm implementation |
|---|---|---|
| Problem framing | Explore suspicious relationships across related entities. | Rules and evidence in the source code. |
| Graph design | Explore nodes, edges, and connected entities. | Implemented graph construction and source-record traceability. |
| Dashboard | Explore page organization and graph readability. | Working application behavior. |
| Debugging | Investigate the Streamlit secrets warning and stalled data generation. | Observed command output and configuration checks. |
| Testing and evaluation | Explore tests, metrics, false positives, false negatives, and leakage checks. | Actual test output and computed evaluation results. |
| Deployment and security | Identify deployment configuration and credential-handling checks. | Successful environment checks and confirmation that secrets are not committed. |

AI helped explore possible solutions and identify areas to investigate. The prompt history alone does not establish that the proposed changes were correct or that all checks passed.

## 5. Human review and validation

My contribution involved working on the project implementation, integrating application components, refining the user interface, managing project data and configuration, troubleshooting issues, and carrying out testing and deployment tasks.

I also worked on improving the project documentation and checking the behavior of the application during development. AI assistance supported the investigation of technical problems and the exploration of possible solutions, while I worked with the project files and environment to apply and verify relevant changes.


## 6. Limitations and responsible use

- The available prompt history may not include every AI interaction.
- The prompts are not a complete transcript of model responses.
- A generated code sample or suggested test is not proof that it was executed successfully.
- Evaluation on synthetic data does not establish real-world fraud detection accuracy.
- Shared contact details, addresses, or providers can have legitimate explanations and do not independently prove fraud.
- Risk scores are intended to prioritize investigation, not to declare fraud proven.
- Deployment, security, and test results must be verified in the actual environment.

## 7. Final disclosure

AI assistants supported parts of the development process by helping explore technical approaches, investigate issues, and consider testing and documentation. I remain responsible for the final repository and for accurately reporting what was implemented and verified.

This document records the prompt history currently available and does not claim to be an exhaustive transcript. Additional original prompt records and validation evidence should be added if recovered.

