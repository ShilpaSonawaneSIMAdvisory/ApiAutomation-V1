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

import json
import requests
import traceback
import pandas as pd
import os

ACCESS_TOKEN = ""
BASE_URL = ""


def readSecrets():
    try:
        with open("secrets.json", "r") as secrets_file:
            secrets = json.load(secrets_file)
            return secrets
    except FileNotFoundError:
        print("Secrets file not found!")
        return None
    except json.JSONDecodeError:
        print("Error decoding JSON from the secrets file.")
        return None


def readMetadata(metadata_path):
    metadata_contents = []
    try:
        for filename in os.listdir(metadata_path):
            file_path = os.path.join(metadata_path, filename)
            if os.path.isfile(file_path):
                with open(file_path, "r") as metadata_file:
                    try:
                        metadata = json.load(metadata_file)
                        metadata_contents.append(metadata)
                    except json.JSONDecodeError:
                        print(f"Error decoding JSON in file: {filename}")
    except FileNotFoundError:
        print("Metadata directory not found!")
    return metadata_contents


def readExcelSheet(file_path, file_name):

    df = pd.read_excel(
        f"{file_path}/{file_name}.xlsx", header=[0, 1], keep_default_na=False
    )
    if df is None:
        raise ValueError(f"Sheet {file_name} not found in the excel file!")

    df.columns = [
        (
            f"{col[0].strip()}::{col[1].strip()}"
            if col[1].strip() != ""
            else col[0].strip()
        )
        for col in df.columns
    ]
    df.columns = (
        df.columns.str.replace("\n", "").str.replace("\\n", "").str.strip().str.upper()
    )
    return df


def performAction(action, url, headers=None, payload=None):
    if action == "GET":
        response = requests.get(url, headers=headers)
    elif action == "POST":
        response = requests.post(url, headers=headers, json=payload)
    elif action == "PUT":
        response = requests.put(url, headers=headers, json=payload)
    elif action == "DELETE":
        response = requests.delete(url, headers=headers)
    else:
        print(f"Unsupported action: {action}")
        return None
    return response


def mapValuestoAttributesFromTestCase(test_case, attributes, entity, isInputOrOutput):
    valueMap = []
    colHeaders = "INPUTS" if isInputOrOutput == "INPUTS" else "OUTPUTS"
    for each_attr in attributes:
        test_case_attr = f"{colHeaders.upper()}::{entity.upper()}::{each_attr.upper()}"
        if test_case_attr not in test_case:
            raise ValueError(
                f"Missing attribute: {each_attr} present in metadata is not present in the input sheet: {test_case_attr}"
            )
        value = str(test_case[test_case_attr]).strip()
        if value.upper() == "NULL" or value.upper() == "NONE":
            value = None
        try:
            if '.' in value:
                value = float(value)
            else:
                value = int(value)
        except:
            pass
        valueMap.append(
            {"key": each_attr, "value": value}
        )
    return valueMap


def processEachStep(
    action,
    entity,
    url,
    isInputOrOutput,
    identifier_attributes=[],
    input_attributes=[],
    responseFromPreviousStep=None,
    test_case={},
):
    if action == "PUT" and responseFromPreviousStep is None:
        raise ValueError("PUT action requires a response from a previous step!")
    elif action == "PUT" and responseFromPreviousStep == "SKIPPED STEP":
        return "SKIPPED STEP"

    global ACCESS_TOKEN
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    identifier_attributes_value_map = mapValuestoAttributesFromTestCase(
        test_case, identifier_attributes, entity, isInputOrOutput
    )

    has_invalid_value = any(
        x["value"] == ""
        or x["value"] is None
        or str(x["value"]).upper() == "NONE"
        or str(x["value"]).upper() == "NULL"
        for x in identifier_attributes_value_map
    )

    if has_invalid_value:
        return "SKIPPED STEP"

    input_attributes_value_map = mapValuestoAttributesFromTestCase(
        test_case, input_attributes, entity, isInputOrOutput
    )

    if action == "POST":
        filters = list(
            map(
                lambda x: {
                    "filterType": "CONDITION",
                    "joinType": "NONE",
                    "operatorType": "EQUALS",
                    "key": x["key"],
                    "value": x["value"],
                    "dataType": "string",
                },
                identifier_attributes_value_map,
            )
        )
        payload = {
            "pager": {"pageNumber": 0, "pageSize": 1},
            "sorters": [{"direction": "DESC", "property": "id"}],
            "filters": filters,
        }
    elif action == "PUT":
        payload = {"data": [responseFromPreviousStep]}
        input_attributes_value_map.extend(identifier_attributes_value_map)
        for each_input_attr in input_attributes_value_map:
            payload["data"][0][each_input_attr["key"]] = each_input_attr["value"]

    global BASE_URL
    url = f"{BASE_URL}{url}"

    response = performAction(action, url, headers=headers, payload=payload)

    if response and (response.status_code == 200 or response.status_code == 201):
        if action == "POST":
            data = response.json()
            total_elements = data.get("totalElements", 0)
            content = data.get("content", [])
            if total_elements <= 0 or len(content) < 1:
                raise ValueError(
                    f"The number of elements returned after applying filters for entity {entity} is less than 1: Elements -- {total_elements} ||| Url -- {url}\nPayload -- {json.dumps(payload)}\n"
                )

            return content[0]
    else:
        data = response.json()
        raise ValueError(
            f"\nMessage:{data['message']}\nNo output returned for entity: {entity}!\nAction -- {action} ||| Response Status code -- {response.status_code} ||| URL -- {url} \nPayload -- {json.dumps(payload)}"
        )


def checkOutputs(entity_output_map, entity, output_attributes, test_case):
    outputAttributesInTestCase = mapValuestoAttributesFromTestCase(
        test_case, output_attributes, entity, "OUTPUTS"
    )
    for index, each_output_attr in enumerate(output_attributes):
        entity_output = entity_output_map.get(entity, {})
        if not entity_output:
            return {"output": False, "reason": "Entity output not found!"}

        valueInTestCase = outputAttributesInTestCase[index]["value"]
        valueFromResult = entity_output.get(each_output_attr)

        if (
            valueInTestCase == ""
            or valueInTestCase is None
            or str(valueInTestCase).upper() == "NONE"
            or str(valueInTestCase).upper() == "NULL"
        ):
            valueInTestCase = "NULL"

        if (
            valueFromResult == ""
            or valueFromResult is None
            or str(valueFromResult).upper() == "NONE"
            or str(valueFromResult).upper() == "NULL"
        ):
            valueFromResult = "NULL"

        if (
            valueFromResult != valueInTestCase
            or outputAttributesInTestCase[index]["key"] != each_output_attr
        ):
            reason = f"Value from Test case: {valueInTestCase} and value from result: {valueFromResult} do not match!"
            print(reason)
            return {"output": False, "reason": reason}
    return {"output": True, "reason": ""}


def main():
    secrets = readSecrets()

    global BASE_URL
    BASE_URL = secrets.get("base_url", "")

    global ACCESS_TOKEN
    ACCESS_TOKEN = secrets.get("access_token", "")
    if not ACCESS_TOKEN:
        print("Access token not found! Exiting...")
        exit()

    output_path = secrets.get("output_path", "outputs")
    if not os.path.exists(output_path):
        os.makedirs(output_path)

    metadata_path = secrets.get("metadata_path", "")
    if not metadata_path or not os.path.exists(metadata_path):
        print("Metadata file has some errors or is missing! Exiting...")
        exit()
    metadata = readMetadata(metadata_path)

    input_excel_path = secrets.get("input_excel_path", "")
    if not input_excel_path or not os.path.exists(input_excel_path):
        print("Excel file path not found! Exiting...")
        exit()

    # Todo iterating over metadata files
    for each_metadata in metadata:
        try:
            tab_name = each_metadata.get("tab_name", "")
            if not tab_name:
                print("Tab name not found for tab:", each_metadata)
                continue

            print(f"Processing tab: {tab_name}")
            inputs_flow = each_metadata["test_case_flow"].get("inputs", [])
            outputs_flow = each_metadata["test_case_flow"].get("outputs", [])

            df = readExcelSheet(input_excel_path, tab_name)

            test_cases = df.to_dict(orient="records")
            totalTestCases = len(test_cases)

            automated_status_column = ["FAIL"] * len(test_cases)
            additional_comments_column = [""] * len(test_cases)

            for index, test_case in enumerate(test_cases):
                print(
                    f"Processing test case: {index+1} out of {totalTestCases} for tab: {tab_name}"
                )
                try:
                    # PROCESS INPUTS
                    for each_step in inputs_flow:
                        sequence = each_step.get("sequence", "")
                        action = each_step.get("action", "")
                        entity = each_step.get("entity", "").upper()
                        url = each_step.get("url", "")

                        if not sequence or not action or not entity or not url:
                            print(f"Missing required fields for test case:", each_step)
                            continue

                        identifier_attributes = each_step.get(
                            "identifier_attributes", []
                        )
                        input_attributes = each_step.get("input_attributes", [])

                        if action != "PUT":
                            responseFromPreviousStep = None

                        responseFromPreviousStep = processEachStep(
                            action,
                            entity,
                            url,
                            "INPUTS",
                            identifier_attributes,
                            input_attributes,
                            responseFromPreviousStep,
                            test_case,
                        )

                    # PROCESS OUTPUTS
                    entity_output_map = {}
                    for each_step in outputs_flow:
                        sequence = each_step.get("sequence", "")
                        action = each_step.get("action", "")
                        entity = each_step.get("entity", "").upper()
                        url = each_step.get("url", "")

                        if not sequence or not action or not entity or not url:
                            print(f"Missing required fields for test case:", each_step)
                            continue

                        identifier_attributes = each_step.get(
                            "identifier_attributes", []
                        )

                        if action != "PUT":
                            responseFromPreviousStep = None

                        responseFromPreviousStep = processEachStep(
                            action,
                            entity,
                            url,
                            "OUTPUTS",
                            identifier_attributes,
                            [],
                            responseFromPreviousStep,
                            test_case,
                        )

                        entity_output_map[entity] = responseFromPreviousStep

                    # CHECK OUTPUTS FOR EACH ENTITY (as it forms the entity output map)
                    for each_step in outputs_flow:
                        output_attributes = each_step.get("output_attributes", [])
                        entity = each_step.get("entity", "").upper()
                        passOrFail = checkOutputs(
                            entity_output_map, entity, output_attributes, test_case
                        )
                        if passOrFail["output"]:
                            automated_status_column[index] = "SUCCESS"
                        else:
                            additional_comments_column[index] = passOrFail["reason"]

                except Exception as e:
                    additional_comments_column[index] = (
                        f"Exception encountered while processing the test case, row -- {index+1} ||| Sequence -- {sequence} ||| Entity -- {entity}\
                            \nException details: {traceback.format_exc()}"
                    )

            df["AUTOMATED_STATUS"] = automated_status_column
            df["ADDITIONAL_COMMENTS"] = additional_comments_column
            df.to_csv(f"{output_path}/{tab_name}_output.csv", index=False)

        except Exception as e:
            print("Exception encoutered while processing tab:", e)
            traceback.print_exc()


if __name__ == "__main__":
    main()
