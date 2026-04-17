# Business User Guide

This guide is for business users who want to use the Salesforce SecuredSOQL Agent without knowing Salesforce object names, field API names, or SOQL.

## Most important idea

This agent works best as a multi-turn drafting partner.

You do not need to provide everything in one message.

A good way to use it is:

1. start with the account and plan year
2. answer the next question the agent asks
3. keep adding one section at a time
4. ask what is still missing
5. ask if it is ready
6. approve upload only when the preview looks correct

## What this agent can help you do

- understand a customer account in business language
- review client priorities, challenges, and growth opportunities
- review spend plans and account-plan context
- prepare an account plan step by step
- validate whether an account plan is ready before upload
- upload an account plan after review and approval

## What you do not need to know

You do not need to know:

- Salesforce object names like `Account` or `Account_Plan__c`
- Salesforce field API names
- SOQL query syntax

You can ask in plain business language instead.

## Best ways to ask

Use prompts like these:

- "Show me Nike client priorities and growth opportunities"
- "What do we know about Acme's strategy and spend?"
- "Help me prepare a 2026 account plan for Nike"
- "Is this account plan ready to upload?"
- "What is still missing from this plan?"

For multi-turn work, short follow-up answers are fine.

Examples:

- "Use Nike"
- "Plan year is 2026"
- "Main goal is upper funnel growth"
- "Q1 is 30k, Q2 is 25k, Q3 is 20k, Q4 is 25k"
- "Primary contact is Jane Doe"

## Main use cases

### 1. Understand an account

Examples:

- "Show me what we know about Nike"
- "Give me the key context for Acme"
- "Show me leadership context for this client"

What the agent will do:

- try to identify the right customer account
- look up accessible Salesforce data
- summarize it in business terms

### 2. Review priorities, goals, and opportunities

Examples:

- "What are Nike's priorities?"
- "Show me growth opportunities for Acme"
- "What are the main challenges and goals for this account?"

What the agent will do:

- translate business concepts like priorities, goals, and opportunities into the right Salesforce fields
- query the accessible data
- summarize the results

### 3. Review spend planning

Examples:

- "Show me the spend plan for Nike"
- "What is the annual and quarterly spend estimate?"

What the agent will do:

- find spend-related account-plan fields
- show what is currently available
- tell you if some requested data was not returned because of Salesforce security policy

### 4. Prepare an account plan

Examples:

- "Help me prepare a 2026 account plan for Nike"
- "Create a draft account plan for Acme next year"

What the agent will do:

- identify the customer account
- infer the plan year when possible
- build the draft in sections:
  - foundation
  - strategy
  - spend plan
  - stakeholders
- tell you what is still missing
- recommend the next best question to answer

This is the main multi-turn use case for business users.

### 5. Review readiness before upload

Examples:

- "Is this plan ready?"
- "What will be written if I approve this?"

What the agent will do:

- calculate a readiness score
- classify the draft as `early`, `partial`, `almost_ready`, or `ready`
- show an upload preview
- keep the plan in draft mode if important information is still missing

### 6. Upload the account plan

Examples:

- "Upload this account plan"
- "Approve and create the plan"

What the agent will do:

- validate the plan
- pause for approval
- upload only after approval

## How the draft workflow works

The account-plan draft is built progressively.

Typical flow:

1. Start the draft
   Example: "Help me prepare a 2026 account plan for Nike"

2. Answer the next question
   Example: "The main goal is upper funnel growth and better measurement confidence"

3. Add spend details
   Example: "Annual budget is 120k and split evenly across quarters"

4. Add stakeholder context
   Example: "Primary contact is Jane Doe and the budget owner is Mark"

5. Ask if it is ready
   Example: "Is this ready to upload?"

6. Approve upload
   Example: "Approve and upload it"

## Recommended multi-turn pattern

The easiest way to work with the agent is to keep each turn focused on one missing section.

### Turn 1: start the draft

Examples:

- "Help me prepare a 2026 account plan for Nike"
- "Start a draft account plan for Acme for 2026"

Goal of this turn:

- identify the account
- identify the year
- open the draft

### Turn 2: provide strategy or goals

Examples:

- "The strategy is to grow consideration and improve measurement confidence"
- "Main goals are upper funnel growth and stronger shopping performance"

Goal of this turn:

- fill the strategy section

### Turn 3: provide client priorities or challenges

Examples:

- "The client is focused on measurement confidence and creative performance"
- "Main challenge is proving incrementality and improving media efficiency"

Goal of this turn:

- fill the business challenge and priority section

### Turn 4: provide growth opportunities

Examples:

- "Biggest opportunity is expanding shopping campaigns"
- "Growth opportunity is better seasonal activation and broader audience coverage"

Goal of this turn:

- fill the growth opportunity section

### Turn 5: provide spend plan

Examples:

- "Annual budget is 120k"
- "Q1 is 30k, Q2 is 30k, Q3 is 30k, Q4 is 30k"

Goal of this turn:

- fill the spend plan
- make sure quarterly values match the annual number

### Turn 6: provide stakeholders

Examples:

- "Primary contact is Jane Doe"
- "Budget owner is Mark"
- "Leadership sponsor is Sarah"

Goal of this turn:

- fill the stakeholder section

### Turn 7: check readiness

Examples:

- "What is still missing?"
- "Is this ready to upload?"
- "Show me the upload preview"

Goal of this turn:

- review the readiness score
- review the upload preview
- check whether anything important is still incomplete

### Turn 8: approve upload

Examples:

- "Approve and upload it"
- "This looks correct, create the plan"

Goal of this turn:

- confirm the final write

## How to answer follow-up questions

When the agent asks for the next missing item, you do not need to restate the whole plan.

Short answers are enough.

Examples:

- Agent: "Which plan year should I use?"
  You: "2026"

- Agent: "What are the main goals or strategy themes?"
  You: "Grow consideration and improve measurement confidence"

- Agent: "Can you provide the quarterly spend breakdown?"
  You: "25k in each quarter"

- Agent: "Who is the budget decision maker?"
  You: "Mark Chen"

The agent is designed to accumulate the draft across turns when the same session is used.

## What to expect from the agent

### It may ask you to choose an account

If more than one Salesforce account matches the company name, the agent may ask you to pick one.

Example:

- "I found multiple Account matches for Acme. Choose one before I continue."

### It may say information is missing

This is normal during draft preparation.

Examples of missing items:

- plan year
- goals or strategy
- growth opportunities
- annual spend
- quarterly spend breakdown
- stakeholder context

This does not mean the draft failed.

It usually means:

- the draft is open
- some sections are already saved
- the agent is guiding you to the next missing section

### It may not show everything you asked for

The Salesforce MCP server applies security rules.

That means:

- some fields may be hidden
- some rows may not be visible
- some filters may be blocked if they use restricted fields

The agent will tell you when this happens. It will not invent missing data.

## Tips for best results

- use the customer name clearly
- mention the plan year when you know it
- answer one missing section at a time if the agent asks for more detail
- ask for readiness before asking to upload
- use the same session for follow-up questions if your UI or integration supports `session_id`
- do not worry about giving perfect wording; business language is fine
- if the agent asks a direct follow-up question, answer that question first before moving to a new topic

## Good prompt examples

- "Help me prepare a 2026 account plan for Nike"
- "The strategy is to grow consideration and improve measurement confidence"
- "The client's main challenge is measurement confidence"
- "Biggest opportunity is shopping expansion"
- "Annual spend is 100k, with 25k per quarter"
- "Leadership context: Jane is the main contact and Mark owns the budget"
- "Show me what is still missing"
- "Is this ready to upload?"
- "Approve and upload the plan"

## Simple checklist

Before upload, try to have:

- the right customer account
- the correct plan year
- goals or strategy
- business challenges or priorities
- growth opportunities
- annual spend target
- quarterly spend breakdown
- stakeholder or leadership context

## If you are using the API through a UI or app

Ask your UI or integration to keep the same `session_id` while you build the draft. That lets the agent carry forward what you already provided instead of starting over each time.

For multi-turn drafting, this is especially important. Without the same `session_id`, the agent may treat each turn like a new request instead of a continuation of the same plan.
