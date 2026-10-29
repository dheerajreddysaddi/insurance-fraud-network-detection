# AI Usage History
## Project: Insurance Fraud Network Detection

### 1. Understanding the Project

**Question 1**

I am working on an insurance fraud network detection project. How can I identify relationships between claims that might be suspicious instead of checking each claim separately?

**Question 2**

How should I represent the connections between claims and related entities in a graph? What should be considered a node and what should be an edge?

**Question 3**

I want the application to show the suspicious connections in a way that is easy to understand. What information should I display for each claim and its connected entities?

### 2. Working on the Application

**Question 4**

I have a Streamlit application for this project. How should I organize the pages so that users can explore the data, view the network, and investigate suspicious claims without everything appearing on one page?

**Question 5**

The network graph is becoming difficult to read when there are too many connected nodes. How can I make the visualization easier to understand without hiding important relationships?

**Question 6**

How can I improve the layout of the Streamlit dashboard so that the metrics, tables, filters, and network visualization look consistent?

### 3. Debugging and Code Issues

*[Fill in before submitting: who sent these messages, e.g. "The messages below were written by <NAME> in a Claude conversation."]*

**Question 7: Red error box in the sidebar (exact messages, one with a screenshot)**

> what is that error on the left side

After the first fix, I sent:

>  the red “No secrets found” box is gone from the sidebar.-- its not gone its still there

Outcome: the app read `st.secrets` before the environment variable. The code was changed to read `APP_PASSCODE` from the environment first. The box stayed because my `.env` file did not exist, so I created it from `.env.example` and restarted the app.



**Question 8: Database load appeared to hang (exact message, then pasted terminal output)**

> python scripts/generate_data.py --scale full --replace 2>&1 | tail -40
> not giving any output even after 5 minutes



### 4. Testing and Validation

**Question 9**

How should I test the main features of the application before deployment? I want to make sure that data loading, filtering, network visualization, and the investigation workflow work correctly.

**Question 10**

Which metrics should I report when evaluating a fraud detection model, and how should I explain false positives and false negatives?

**Question 11**

How can I check for data leakage and make sure that the evaluation results represent how the model might perform on unseen data?


**Question 12**

The application works locally, but I am having trouble deploying it to Streamlit Community Cloud. How should I check the repository configuration, dependency file, entry-point script, and secrets?

**Question 13**

How can I make sure that database credentials and other secrets are not committed to GitHub and are configured correctly in the deployment environment?


### 5. How AI Was Used

AI was used as a supporting tool during development to explore technical approaches, understand unfamiliar concepts, investigate errors, review selected code, improve the application interface, and resolve environment, deployment, and Git-related questions.

The assistance was most useful when a problem required understanding an error message, comparing implementation options, or identifying what to investigate next. Suggestions were considered in the context of the existing project rather than assumed to be correct automatically.

The project's limitations are documented in the "Known limitations" section of `README.md` and in `DESIGN_DECISIONS.md`.

### 6. My Contribution

My contribution involved working on the project implementation, integrating application components, refining the user interface, managing project data and configuration, troubleshooting issues, and carrying out testing and deployment tasks.

I also worked on improving the project documentation and checking the behavior of the application during development. AI assistance supported the investigation of technical problems and the exploration of possible solutions, while I worked with the project files and environment to apply and verify relevant changes.
