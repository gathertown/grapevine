from datetime import datetime
from typing import Literal, TypedDict

from pydantic import BaseModel

HubSpotSearchDirection = Literal["ASCENDING", "DESCENDING"]


class HubSpotSearchReqSort(TypedDict):
    propertyName: str
    direction: HubSpotSearchDirection


HubSpotFilterOperator = Literal[
    "LT",
    "LTE",
    "GT",
    "GTE",
    "EQ",
    "NEQ",
    "BETWEEN",
    "IN",
    "NOT_IN",
    "HAS_PROPERTY",
    "NOT_HAS_PROPERTY",
    "CONTAINS_TOKEN",
    "NOT_CONTAINS_TOKEN",
]


class HubSpotSearchReqFilter(TypedDict):
    propertyName: str
    operator: HubSpotFilterOperator
    value: str


class HubspotSearchReqFilterGroup(TypedDict):
    filters: list[HubSpotSearchReqFilter]


class HubSpotSearchReq(TypedDict):
    limit: int
    after: int | None
    properties: list[str]
    sorts: list[HubSpotSearchReqSort]
    filterGroups: list[HubspotSearchReqFilterGroup]


HubSpotSearchByDateField = Literal["createdate", "hs_lastmodifieddate"]


class HubSpotSearchDateFilter(TypedDict):
    start: datetime
    end: datetime


class HubSpotSearchOptions(TypedDict):
    properties: list[str]
    date_filter: HubSpotSearchDateFilter
    search_by: HubSpotSearchByDateField


def build_search_request(
    search_options: HubSpotSearchOptions,
    after: int | None = None,
    limit: int = 50,
) -> HubSpotSearchReq:
    start_timestamp = int(search_options["date_filter"]["start"].timestamp() * 1000)
    end_timestamp = int(search_options["date_filter"]["end"].timestamp() * 1000)

    return HubSpotSearchReq(
        limit=limit,
        after=after,
        properties=search_options["properties"],
        sorts=[
            HubSpotSearchReqSort(
                propertyName=search_options["search_by"],
                direction="DESCENDING",
            )
        ],
        filterGroups=[
            HubspotSearchReqFilterGroup(
                filters=[
                    HubSpotSearchReqFilter(
                        propertyName=search_options["search_by"],
                        operator="GTE",
                        value=str(start_timestamp),
                    ),
                    HubSpotSearchReqFilter(
                        propertyName=search_options["search_by"],
                        operator="LT",
                        value=str(end_timestamp),
                    ),
                ]
            )
        ],
    )


class HubSpotSearchRes[T](BaseModel):
    results: list[T]
    after: int | None
