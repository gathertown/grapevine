from typing import Annotated

from pydantic import Field

from connectors.base.document_source import DocumentSource

DocumentIdAnnotation = Annotated[
    str,
    Field(
        description=f"""
Document ID as returned by search tools. Document IDs uniquely identify documents in the system. Each `source` type has its own ID construction pattern:

`source="{DocumentSource.GITHUB_PRS.value}"` (GitHub Pull Requests): {{repo_id}}_pr_{{pr_number}}
- Example: "123456789_pr_12345"

`source="{DocumentSource.LINEAR.value}"` (Linear Issues): issue_{{issue_id}}
- Example: "issue_11223344-5566-7788-9900-aabbccddeeff"

`source="{DocumentSource.SLACK.value}"` (Slack Channels): {{channel_id}}_{{date}}
- Example: "C1234567890_2024-01-15"

`source="{DocumentSource.NOTION.value}"` (Notion Pages): notion_page_{{page_id}}
- Example: "notion_page_abcdefgh-1234-6789-0zxy-w01234567890"
- To convert Notion URLs to `page_id`, format the 32 character string at the end of the URL by inserting hyphens (-) in the following pattern: 8-4-4-4-12 (each number is the length of characters between the hyphens).
  - Example: https://www.notion.so/acmeco/An-Internal-Page-1234567890abcedfhijklmnopqrstuvw ends with 19fbc7eac3d1802dbf0ecd39a2c245ee, so the `page_id` is 19fbc7ea-c3d1-802d-bf0e-cd39a2c245ee, and the full document ID is `notion_page_19fbc7ea-c3d1-802d-bf0e-cd39a2c245ee`.

`source="{DocumentSource.GITHUB_CODE.value}"` (GitHub Code Files): github_file_{{owner}}/{{repo}}/{{file_path}}
- Example: "github_file_octocat/Hello-World/README.md" for the file `README.md` in the repo `Hello-World` owned by `octocat`
- Example: "github_file_facebook/react/packages/react/src/React.js" for the file at path `packages/react/src/React.js` in the `react` repo owned by `facebook`

`source="{DocumentSource.GOOGLE_DRIVE.value}"` (Google Drive Files): google_drive_file_{{file_id}}
- Example: "google_drive_file_1a2b3c4d5e6f7g8h9i0j" for a Google Drive file with ID `1a2b3c4d5e6f7g8h9i0j`
- The file_id is the unique identifier assigned by Google Drive to each file

`source="{DocumentSource.GOOGLE_EMAIL.value}"` (Google Email Messages): google_email_message_{{message_id}}
- Example: "google_email_message_18a1b2c3d4e5f6g7" for a Gmail message with ID `18a1b2c3d4e5f6g7`
- The message_id is the unique identifier assigned by Gmail to each message

`source="{DocumentSource.HUBSPOT_DEAL.value}"`, `"{DocumentSource.HUBSPOT_TICKET.value}"`, `"{DocumentSource.HUBSPOT_COMPANY.value}"`, `"{DocumentSource.HUBSPOT_CONTACT.value}"` (HubSpot Objects): hubspot_{{object_type}}_{{record_id}}
- Example: "hubspot_deal_12345678" for a HubSpot deal with ID `12345678`
- Example: "hubspot_ticket_87654321" for a HubSpot ticket with ID `87654321`
- Example: "hubspot_company_11223344" for a HubSpot company with ID `11223344`
- Example: "hubspot_contact_99887766" for a HubSpot contact with ID `99887766`
- The object_type matches the source type (deal, ticket, company, contact) and record_id is HubSpot's internal ID

`source="{DocumentSource.SALESFORCE.value}"` (Salesforce Objects): salesforce_{{object_type}}_{{record_id}}
- Example: "salesforce_account_001xx000003DGb2AAG" for a Salesforce Account with ID `001xx000003DGb2AAG`
- Example: "salesforce_opportunity_006xx000003DGb2AAG" for a Salesforce Opportunity with ID `006xx000003DGb2AAG`
- Example: "salesforce_case_500xx000003DGb2AAG" for a Salesforce Case with ID `500xx000003DGb2AAG`
- Example: "salesforce_contact_003xx000003DGb2AAG" for a Salesforce Contact with ID `003xx000003DGb2AAG`
- Example: "salesforce_lead_00Qxx000003DGb2AAG" for a Salesforce Lead with ID `00Qxx000003DGb2AAG`
- The object_type is lowercase (account, opportunity, case, contact, lead) and record_id is Salesforce's 18-character ID

`source="{DocumentSource.JIRA.value}"` (Jira Issues): jira_issue_{{issue_id}}
- Example: "jira_issue_10218" for a Jira issue with internal ID `10218`
- The issue_id is the unique Jira internal issue identifier (numeric string format), which is more stable than issue keys

`source="{DocumentSource.CONFLUENCE.value}"` (Confluence Pages): confluence_page_{{page_id}}
- Example: "confluence_page_123456789" for a Confluence page with ID `123456789`
- The page_id is the unique Confluence internal page identifier (numeric string format)

`source="{DocumentSource.GONG.value}"` (Gong Calls): gong_call_{{call_id}}
- Example: "gong_call_1234567890123456789" for a Gong call with ID `1234567890123456789`
- The call_id is the unique identifier assigned by Gong to each call recording

`source="{DocumentSource.GATHER.value}"` (Gather Meetings): gather_meeting_{{meeting_id}}
- Example: "gather_meeting_a1b2c3d4-e5f6-7890-abcd-ef1234567890" for a Gather meeting with ID `a1b2c3d4-e5f6-7890-abcd-ef1234567890`
- The meeting_id is the unique identifier for Gather meetings (UUID format)

IMPORTANT: double check that your `document_id` is formatted correctly for the `source` type based on the rules and examples above!
"""
    ),
]
