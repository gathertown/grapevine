"""Internal Linear ticket management tool for agent use only."""

import asyncpg

from src.clients.linear_factory import get_linear_client_for_tenant
from src.clients.ssm import SSMClient
from src.utils.logging import get_logger

logger = get_logger(__name__)


# Tool schema for OpenAI
LINEAR_TOOL_SCHEMA = {
    "type": "function",
    "name": "manage_linear_ticket",
    "description": """Manage a Linear ticket by creating or updating it.

This tool allows direct manipulation of Linear tickets for mechanical operations without the overhead of the full triage agent workflow.

Returns:
- {"success": bool, "message": str, "issue": dict | None, "team": dict | None}
""",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "list_teams",
                    "lookup_team",
                    "get_ticket",
                    "create_ticket",
                    "change_status",
                    "assign",
                    "set_priority",
                    "link_issue",
                    "edit_title",
                    "edit_description",
                ],
                "description": "Action to perform: 'list_teams' to get all available teams with their names and shortcodes, 'lookup_team' to get team_id from shortcode (e.g., 'ENG', 'PROD'), 'get_ticket' to retrieve ticket details, 'create_ticket' to create ticket, 'change_status' to update status, 'assign' to assign to user or null to unassign, 'set_priority' to set priority (1-4), 'link_issue' to link issues, 'edit_title' to change title, 'edit_description' to change description",
            },
            "issue_identifier": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
                "description": "Issue identifier for change_status action (e.g., 'ENG-123', 'PROD-456'). Required for change_status, not used for create_ticket.",
            },
            "status": {
                "anyOf": [
                    {"type": "string", "enum": ["done", "in_progress", "todo", "canceled"]},
                    {"type": "null"},
                ],
                "description": "Status for change_status action. Maps to Linear workflow states: done=completed, in_progress=started, todo=unstarted, canceled=canceled",
            },
            "title": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
                "description": "Title for create_ticket or edit_title action",
            },
            "description": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
                "description": "Description for create_ticket or edit_description action. IMPORTANT for edit_description: ALWAYS use get_ticket first to read the existing description, then append/modify while preserving all existing information. Never overwrite the entire description without reading it first.",
            },
            "team_id": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
                "description": "Linear team ID (UUID) for create_ticket action. Use lookup_team to get this from a team shortcode.",
            },
            "team_key": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
                "description": "Team shortcode for lookup_team action (e.g., 'ENG', 'PROD', 'INFRA'). Extract from ticket IDs like ENG-123.",
            },
            "assignee_email": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
                "description": "Email address of user to assign for assign action. Pass null to unassign the ticket.",
            },
            "priority": {
                "anyOf": [{"type": "integer"}, {"type": "null"}],
                "description": "Priority level for set_priority action: 1=Urgent, 2=High, 3=Medium, 4=Low (required for set_priority)",
            },
            "related_issue_identifier": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
                "description": "Related issue identifier for link_issue action (e.g., 'ENG-456'). Required for link_issue.",
            },
        },
        "required": [
            "action",
            "issue_identifier",
            "status",
            "title",
            "description",
            "team_id",
            "team_key",
            "assignee_email",
            "priority",
            "related_issue_identifier",
        ],
        "additionalProperties": False,
    },
    "strict": True,
}


async def execute_manage_linear_ticket(
    tenant_id: str,
    db_pool: asyncpg.Pool,
    action: str,
    issue_identifier: str | None = None,
    status: str | None = None,
    title: str | None = None,
    description: str | None = None,
    team_id: str | None = None,
    team_key: str | None = None,
    assignee_email: str | None = None,
    priority: int | None = None,
    related_issue_identifier: str | None = None,
) -> dict:
    """Execute Linear ticket management operation.

    Args:
        tenant_id: Tenant ID for authentication
        db_pool: Database pool for Linear auth service
        action: Action to perform ('create_ticket', 'change_status', 'assign', 'set_priority', 'link_issue')
        issue_identifier: Issue identifier (e.g., 'ENG-123')
        status: Status to set for change_status
        title: Title for create_ticket
        description: Description for create_ticket
        team_id: Linear team ID for create_ticket
        assignee_email: Email for assign action
        priority: Priority (1-4) for set_priority action
        related_issue_identifier: Related issue for link_issue action

    Returns:
        Dict with success, message, and optional issue data
    """
    logger.info(
        f"execute_manage_linear_ticket - action: {action}, issue: {issue_identifier}, status: {status}"
    )

    # Validate required parameters for each action
    if action == "list_teams":
        # No parameters required for list_teams
        pass
    elif action == "lookup_team":
        if not team_key:
            return {
                "success": False,
                "message": "team_key is required for lookup_team action",
                "issue": None,
                "team": None,
            }
    elif action == "get_ticket":
        if not issue_identifier:
            return {
                "success": False,
                "message": "issue_identifier is required for get_ticket action",
                "issue": None,
            }
    elif action == "change_status":
        if not issue_identifier or not status:
            return {
                "success": False,
                "message": "issue_identifier and status are required for change_status action",
                "issue": None,
            }
    elif action == "create_ticket":
        if not title or not description or not team_id:
            return {
                "success": False,
                "message": "title, description, and team_id are required for create_ticket action",
                "issue": None,
            }
    elif action == "assign":
        if not issue_identifier:
            return {
                "success": False,
                "message": "issue_identifier is required for assign action",
                "issue": None,
            }
    elif action == "set_priority":
        if not issue_identifier or priority is None:
            return {
                "success": False,
                "message": "issue_identifier and priority are required for set_priority action",
                "issue": None,
            }
        if priority not in [1, 2, 3, 4]:
            return {
                "success": False,
                "message": "priority must be 1 (Urgent), 2 (High), 3 (Medium), or 4 (Low)",
                "issue": None,
            }
    elif action == "link_issue":
        if not issue_identifier or not related_issue_identifier:
            return {
                "success": False,
                "message": "issue_identifier and related_issue_identifier are required for link_issue action",
                "issue": None,
            }
    elif action == "edit_title":
        if not issue_identifier or not title:
            return {
                "success": False,
                "message": "issue_identifier and title are required for edit_title action",
                "issue": None,
            }
    elif action == "edit_description":
        if not issue_identifier or not description:
            return {
                "success": False,
                "message": "issue_identifier and description are required for edit_description action",
                "issue": None,
            }
    else:
        return {
            "success": False,
            "message": f"Unknown action '{action}'. Must be one of: list_teams, lookup_team, get_ticket, create_ticket, change_status, assign, set_priority, link_issue, edit_title, edit_description",
            "issue": None,
        }

    try:
        # Create Linear client for this tenant
        ssm_client = SSMClient()
        linear_client = await get_linear_client_for_tenant(tenant_id, ssm_client, db_pool)

        # Handle list_teams action (read-only)
        if action == "list_teams":
            logger.info("Listing all available teams")
            try:
                teams = linear_client.get_public_teams()

                # Also try to get team keys by querying each team
                # Linear SDK returns LinearTeam objects with id and name
                teams_with_keys = []
                for team in teams:
                    # Try to get the full team details including key
                    team_query = """
                    query($teamId: String!) {
                        team(id: $teamId) {
                            id
                            name
                            key
                        }
                    }
                    """
                    try:
                        result = linear_client._make_request(team_query, {"teamId": team.id})
                        team_data = result.get("team", {})
                        teams_with_keys.append(
                            {
                                "id": team_data.get("id", team.id),
                                "name": team_data.get("name", team.name),
                                "key": team_data.get("key", ""),
                            }
                        )
                    except Exception as e:
                        logger.warning(f"Failed to get key for team {team.name}: {e}")
                        teams_with_keys.append(
                            {
                                "id": team.id,
                                "name": team.name,
                                "key": "",
                            }
                        )

                teams_list = "\n".join(
                    [
                        f"- {team['name']} (shortcode: {team['key'] or 'N/A'}, id: {team['id']})"
                        for team in teams_with_keys
                    ]
                )

                return {
                    "success": True,
                    "message": f"Found {len(teams_with_keys)} teams:\n{teams_list}",
                    "teams": teams_with_keys,
                }
            except Exception as e:
                logger.error(f"Failed to list teams: {e}")
                return {
                    "success": False,
                    "message": f"Failed to list teams: {str(e)}",
                    "teams": [],
                }

        # Handle lookup_team action (read-only)
        if action == "lookup_team":
            assert team_key is not None
            logger.info(f"Looking up team by key: {team_key}")
            team_data = linear_client.get_team_by_key(team_key)

            if not team_data:
                return {
                    "success": False,
                    "message": f"Could not find team with key '{team_key}'. Please ask the user for the correct team shortcode.",
                    "issue": None,
                    "team": None,
                }

            return {
                "success": True,
                "message": f"Found team {team_data.get('name')} (key: {team_key})",
                "issue": None,
                "team": {
                    "id": team_data.get("id"),
                    "name": team_data.get("name"),
                    "key": team_data.get("key"),
                },
            }

        # Handle get_ticket action (read-only)
        if action == "get_ticket":
            assert issue_identifier is not None
            logger.info(f"Fetching issue {issue_identifier}")
            issue_data = linear_client.get_issue_by_identifier(issue_identifier)

            if not issue_data:
                return {
                    "success": False,
                    "message": f"Could not find issue {issue_identifier}",
                    "issue": None,
                }

            return {
                "success": True,
                "message": f"Retrieved {issue_identifier}",
                "issue": {
                    "identifier": issue_data.get("identifier"),
                    "title": issue_data.get("title"),
                    "description": issue_data.get("description"),
                    "url": issue_data.get("url"),
                    "state": issue_data.get("state", {}).get("name"),
                    "priority": issue_data.get("priority"),
                    "assignee": (
                        issue_data.get("assignee", {}).get("name")
                        if issue_data.get("assignee")
                        else None
                    ),
                    "creator": (
                        issue_data.get("creator", {}).get("name")
                        if issue_data.get("creator")
                        else None
                    ),
                    "team": issue_data.get("team", {}).get("name"),
                    "createdAt": issue_data.get("createdAt"),
                    "updatedAt": issue_data.get("updatedAt"),
                },
            }

        # Handle create_ticket action
        if action == "create_ticket":
            logger.info(f"Creating new issue: {title}")
            create_result = linear_client.create_issue(
                {
                    "title": title,
                    "description": description,
                    "teamId": team_id,
                }
            )

            if not create_result.get("success"):
                return {
                    "success": False,
                    "message": f"Failed to create issue: {title}",
                    "issue": None,
                }

            created_issue = create_result.get("issue", {})
            return {
                "success": True,
                "message": f"Created {created_issue.get('identifier')}: {title}",
                "issue": {
                    "identifier": created_issue.get("identifier"),
                    "title": created_issue.get("title"),
                    "url": created_issue.get("url"),
                    "state": created_issue.get("state", {}).get("name"),
                },
            }

        # All other actions require fetching the issue first
        # issue_identifier is guaranteed to be non-None here due to validation above
        assert issue_identifier is not None
        logger.info(f"Fetching issue {issue_identifier}")
        issue_data = linear_client.get_issue_by_identifier(issue_identifier)

        if not issue_data:
            return {
                "success": False,
                "message": f"Could not find issue {issue_identifier}",
                "issue": None,
            }

        # Handle assign action (including unassign when assignee_email is None)
        if action == "assign":
            if assignee_email is None:
                # Unassign the ticket
                logger.info(f"Unassigning {issue_identifier}")
                update_result = linear_client.update_issue(issue_data["id"], {"assigneeId": None})

                if not update_result.get("success"):
                    return {
                        "success": False,
                        "message": f"Failed to unassign issue {issue_identifier}",
                        "issue": None,
                    }

                return {
                    "success": True,
                    "message": f"Unassigned {issue_identifier}",
                    "issue": {
                        "identifier": issue_identifier,
                        "title": issue_data.get("title"),
                        "assignee": None,
                    },
                }
            else:
                # Assign to a user
                logger.info(f"Looking up user by email: {assignee_email}")
                user_data = linear_client.get_user_by_email(assignee_email)

                if not user_data:
                    return {
                        "success": False,
                        "message": f"Could not find user with email {assignee_email}",
                        "issue": None,
                    }

                logger.info(f"Assigning {issue_identifier} to {user_data['name']}")
                update_result = linear_client.update_issue(
                    issue_data["id"], {"assigneeId": user_data["id"]}
                )

                if not update_result.get("success"):
                    return {
                        "success": False,
                        "message": f"Failed to assign issue {issue_identifier}",
                        "issue": None,
                    }

                return {
                    "success": True,
                    "message": f"Assigned {issue_identifier} to {user_data['name']}",
                    "issue": {
                        "identifier": issue_identifier,
                        "title": issue_data.get("title"),
                        "assignee": user_data["name"],
                    },
                }

        # Handle set_priority action
        if action == "set_priority":
            assert priority is not None
            logger.info(f"Setting priority for {issue_identifier} to {priority}")
            update_result = linear_client.update_issue(issue_data["id"], {"priority": priority})

            if not update_result.get("success"):
                return {
                    "success": False,
                    "message": f"Failed to set priority for {issue_identifier}",
                    "issue": None,
                }

            priority_labels = {1: "Urgent", 2: "High", 3: "Medium", 4: "Low"}
            return {
                "success": True,
                "message": f"Set {issue_identifier} priority to {priority_labels[priority]}",
                "issue": {
                    "identifier": issue_identifier,
                    "title": issue_data.get("title"),
                    "priority": priority,
                },
            }

        # Handle link_issue action
        if action == "link_issue":
            assert related_issue_identifier is not None
            logger.info(f"Fetching related issue {related_issue_identifier}")
            related_issue = linear_client.get_issue_by_identifier(related_issue_identifier)

            if not related_issue:
                return {
                    "success": False,
                    "message": f"Could not find related issue {related_issue_identifier}",
                    "issue": None,
                }

            logger.info(f"Linking {issue_identifier} to {related_issue_identifier}")
            relation_result = linear_client.create_issue_relation(
                issue_data["id"], related_issue["id"]
            )

            if not relation_result.get("success"):
                return {
                    "success": False,
                    "message": f"Failed to link {issue_identifier} to {related_issue_identifier}",
                    "issue": None,
                }

            return {
                "success": True,
                "message": f"Linked {issue_identifier} to {related_issue_identifier}",
                "issue": {
                    "identifier": issue_identifier,
                    "title": issue_data.get("title"),
                    "related_to": related_issue_identifier,
                },
            }

        # Handle edit_title action
        if action == "edit_title":
            assert title is not None
            logger.info(f"Updating title for {issue_identifier}")
            update_result = linear_client.update_issue(issue_data["id"], {"title": title})

            if not update_result.get("success"):
                return {
                    "success": False,
                    "message": f"Failed to update title for {issue_identifier}",
                    "issue": None,
                }

            return {
                "success": True,
                "message": f"Updated title for {issue_identifier} to: {title}",
                "issue": {
                    "identifier": issue_identifier,
                    "title": title,
                },
            }

        # Handle edit_description action
        if action == "edit_description":
            assert description is not None
            logger.info(f"Updating description for {issue_identifier}")
            update_result = linear_client.update_issue(
                issue_data["id"], {"description": description}
            )

            if not update_result.get("success"):
                return {
                    "success": False,
                    "message": f"Failed to update description for {issue_identifier}",
                    "issue": None,
                }

            return {
                "success": True,
                "message": f"Updated description for {issue_identifier}",
                "issue": {
                    "identifier": issue_identifier,
                    "title": issue_data.get("title"),
                    "description": description[:100] + "..."
                    if len(description) > 100
                    else description,
                },
            }

        # Handle change_status action

        # Map abstract status to Linear state type
        status_type_map = {
            "done": "completed",
            "in_progress": "started",
            "todo": "unstarted",
            "canceled": "canceled",
        }

        target_state_type = status_type_map.get(status) if status else None
        if not target_state_type:
            return {
                "success": False,
                "message": f"Invalid status '{status}'. Must be one of: done, in_progress, todo, canceled",
                "issue": None,
            }

        # Get team states to find the right state ID
        issue_team_id = issue_data.get("team", {}).get("id")
        if not issue_team_id:
            return {
                "success": False,
                "message": f"Could not determine team for issue {issue_identifier}",
                "issue": None,
            }

        logger.info(f"Fetching workflow states for team {issue_team_id}")
        team_states = linear_client.get_team_states(issue_team_id)

        # Find the first state matching the target type
        target_state = next((s for s in team_states if s.get("type") == target_state_type), None)

        if not target_state:
            return {
                "success": False,
                "message": f"Could not find a workflow state for '{status}' (type: {target_state_type}) in team",
                "issue": None,
            }

        # Update the issue
        logger.info(
            f"Updating issue {issue_identifier} to state {target_state['name']} (ID: {target_state['id']})"
        )
        update_result = linear_client.update_issue(
            issue_data["id"], {"stateId": target_state["id"]}
        )

        if not update_result.get("success"):
            return {
                "success": False,
                "message": f"Failed to update issue {issue_identifier}",
                "issue": None,
            }

        # Return success with updated issue data
        updated_issue = update_result.get("issue", {})
        return {
            "success": True,
            "message": f"Updated {issue_identifier} to '{target_state['name']}'",
            "issue": {
                "identifier": updated_issue.get("identifier"),
                "title": updated_issue.get("title"),
                "state": updated_issue.get("state", {}).get("name"),
                "assignee": (
                    updated_issue.get("assignee", {}).get("name")
                    if updated_issue.get("assignee")
                    else None
                ),
            },
        }

    except Exception as e:
        logger.error(f"Error managing Linear ticket: {e}")
        return {
            "success": False,
            "message": f"Error managing ticket: {str(e)}",
            "issue": None,
        }
