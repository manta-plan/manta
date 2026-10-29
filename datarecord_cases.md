## Use cases for DataRecords (part of step 1)

### FE Load

The frontend user needs to be able to see a list of datarecords present in the current workspace. Upon selecting one to inspect further, the frontend needs to be able to open a Quack connection between its in-browser hosted version of DuckDB and an instance opened on the server side. The server needs to scope access credentials via duckdb appropriately.

### FE Edits

When clicking through and editing scenario data in the GUI, the frontend can generate changes to the attribute data. Those changes should be able to be "flattened" and stored as a record on the backend side.

### Playbook runs

A playbook run will modify a workspace by creating new datarecords that are the results of blocks. Ideologically, the block is a function that transforms a datarecord and returns a new one, serialized into the Store (in the workspace). A full playbook run will result in multiple records being written out. Datarecords need to be accessible from the prefect runners as well as the backend.

### Backend (rehash)

The backend is going to be responsible for spinning up the DuckDB instance-backed renditions of datarecord, updating it in response to playbook step completions. it also will take the frontend changes and store them for playbooks to be able to access as well

### Backend (cont.)

It should be possible to inventory and query a workspace through a set of REST API methods.
