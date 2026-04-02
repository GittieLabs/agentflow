# Foreach Workflow Guide (Resume Conversion)

AgentFlow supports repeating operations over arrays of data using the `foreach` keyword on workflow nodes. This is extremely useful for bulk item processing, such as analyzing lists of contracts or converting pools of PDF resumes into structured JSON output.

This guide walks through assembling a **Resume Conversion pipeline**. The pipeline extracts resumes from an API tool call, iterates through each candidate's resume individually in parallel, and then aggregates the results.

## 1. Defining the Agent Functions

We divide the problem into two parts:
1. **The extraction handler** which fetches resumes from a directory or an external API tool result and returns an array.
2. **The document conversion agent** which evaluates the candidate and formats their details into a structured data format.

### The Parsing Handler

First, we attach a simple Python handler function to parse a PDF or fetch a directory list into a flat JSON list.

This handler will populate our list into the node's `artifacts` explicitly so it can be iterated upon.

```python
from agentflow.types import NodeOutput

async def extract_resume_batch(message: str, prior_outputs: dict) -> NodeOutput:
    # Normally you would fetch from an API or disk here
    candidate_list = [
        {"id": "user1", "resume_text": "Experienced Python Engineer..."},
        {"id": "user2", "resume_text": "Data Scientist with 5 years..."}
    ]
    
    return NodeOutput(
        node_id="extract_resumes",
        agent_id="extract_batch_handler",
        text=f"Extracted {len(candidate_list)} resumes to process.",
        artifacts={"resumes": candidate_list}
    )
```

### The Conversion Agent

Create `agent/resume_converter.prompt.md`:

```yaml
---
name: resume_converter
description: Processes a single candidate resume string into structured JSON.
provider: anthropic
model: claude-sonnet-4-6
temperature: 0.1
---
You are an expert technical recruiter analyzing resumes.

Extract the following information exclusively in JSON format.
- "name"
- "years_experience"
- "core_skills"

Data to process:
{{ message }}
```

## 2. Assembling the DAG

Now, we write the YAML file that sequences the handler that extracts the array, directly into the `foreach` node that iterates the array.

Create `workflows/resume_conversion.workflow.md`:

```yaml
---
name: resume_batch_conversion
trigger: manual
nodes:
  - id: extract_resumes
    handler: extract_resume_batch
    next: [convert_each]
  
  - id: convert_each
    agent: resume_converter
    foreach: "extract_resumes.artifacts.resumes"
    mode: parallel
    next: [aggregate_results]

  - id: aggregate_results
    handler: compile_final_report
    inputs:
      message: "convert_each.artifacts.results"
---
Converts a batch of candidate resumes into a combined structured JSON payload for external databases.
```

## 3. How Foreach Injects Variables

Behind the scenes, when the `WorkflowExecutor` reaches the `convert_each` node, it loops over each item in the referenced list (`extract_resumes.artifacts.resumes`).

For each loop iteration, the `AgentExecutor` injects loop-scope variables automatically into the context mapping:
- `loop_index`: The numerical index.
- `loop_item`: The current resume dictionary.

Behind the curtains, your `resume_converter` agent actually receives `loop_item` dynamically mapped as the `message` (or within the kwargs if handling manually). The result of each parallel or synchronous agent invocation is appended into a single resulting `NodeOutput` where `artifacts["results"]` holds an array of all execution completions for downstream nodes (like `aggregate_results`).

## 4. Run the Pipeline

Simply invoke the executor as normal. The `WorkflowDAG` will automatically handle fanning out the executions depending on your `mode` assignment (Sync vs Parallel).

```python
from agentflow import WorkflowExecutor

# Assuming loader has registered YAML files
executor = WorkflowExecutor(
    config=loader.get_workflow("resume_batch_conversion")[0],
    runner_factory=runner_factory,
    handlers={
        "extract_resume_batch": extract_resume_batch,
        "compile_final_report": compile_final_report
    }
)

outputs = await executor.run(session_id="session-resumes")

# Extract the final list:
print(outputs[-1].text)
```
