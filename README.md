# automation-v2
Automation script version 2 - simadvisory


#### Author: Sanket Tantia
#### Created on: 2024-04-29
#### Last modified on: 2024-05-03
#### Description: This script uses the metadata and the business test case sheet to run automations
# for each test case to check whether they have passed or fail based on the output criteria for each test case.
#### Assumptions:
# 1. The metadata file has the correct structure and all the required fields.
# 2. Bearer token exists in the secrets file and is valid.
# 3. The API endpoints are correct and the actions are supported.
# 4. A POST(filter) request is always before a PUT reqsouest so that its response can be used to construct the PUT payload.
# 5. The output function will only use attributes from the response of the last step in the sequence.

