// Import monochrome SVG files as URLs
import slackSvg from '../integration_logos/slack.png';
import notionSvg from '../integration_logos/notion.png';
import githubSvg from '../integration_logos/github.png';
import linearSvg from '../integration_logos/linear.png';
import googleDriveSvg from '../integration_logos/google_drive.png';
import googleEmailSvg from '../integration_logos/google_email.svg';
import salesforceSvg from '../integration_logos/salesforce.png';
import hubspotSvg from '../integration_logos/hubspot.png';
import jiraPng from '../integration_logos/jira.png';
import confluencePng from '../integration_logos/confluence.png';
import gmailPng from '../integration_logos/gmail.png';
import asanaPng from '../integration_logos/asana.png';
import gongPng from '../integration_logos/gong.png';
import granolaPng from '../integration_logos/granola.png';
import intercomPng from '../integration_logos/intercom.png';
import zendeskPng from '../integration_logos/zendesk.png';
import trelloPng from '../integration_logos/trello.png';
import gatherPng from '../integration_logos/gather.png';
import snowflakePng from '../integration_logos/snowflake.png';
import attioSvg from '../integration_logos/attio.svg';
import firefliesSvg from '../integration_logos/fireflies.svg';
import gitlabSvg from '../integration_logos/gitlab.svg';
import clickupSvg from '../integration_logos/clickup.svg';
import pylonSvg from '../integration_logos/pylon.svg';
import mondaySvg from '../integration_logos/monday.svg';
import pipedrivePng from '../integration_logos/pipedrive.png';
import figmaSvg from '../integration_logos/figma.svg';
import posthogPng from '../integration_logos/posthog.png';
import canvaPng from '../integration_logos/canva.png';
import teamworkSvg from '../integration_logos/teamwork.svg';

interface IconProps {
  size?: number;
}

const borderStyle = {
  borderRadius: 7.5,
  border: '0.5px solid rgba(0, 0, 0, 0.1)',
};

// Create React components that use the monochrome SVG files as img sources
export const SlackIcon = ({ size = 48 }: IconProps) => (
  <img
    src={slackSvg}
    alt="Slack"
    width={size}
    height={size}
    draggable={false}
    style={borderStyle}
  />
);

export const NotionIcon = ({ size = 48 }: IconProps) => (
  <img
    src={notionSvg}
    alt="Notion"
    width={size}
    height={size}
    draggable={false}
    style={borderStyle}
  />
);

export const GitHubIcon = ({ size = 48 }: IconProps) => (
  <img
    src={githubSvg}
    alt="GitHub"
    width={size}
    height={size}
    draggable={false}
    style={borderStyle}
  />
);

export const LinearIcon = ({ size = 48 }: IconProps) => (
  <img
    src={linearSvg}
    alt="Linear"
    width={size}
    height={size}
    draggable={false}
    style={borderStyle}
  />
);

export const GoogleDriveIcon = ({ size = 48 }: IconProps) => (
  <img
    src={googleDriveSvg}
    alt="Google Drive"
    width={size}
    height={size}
    draggable={false}
    style={borderStyle}
  />
);

export const GoogleEmailIcon = ({ size = 48 }: IconProps) => (
  <img src={googleEmailSvg} alt="Google Email" width={size} height={size} draggable={false} />
);

export const SalesforceIcon = ({ size = 48 }: IconProps) => (
  <img
    src={salesforceSvg}
    alt="Salesforce"
    width={size}
    height={size}
    draggable={false}
    style={borderStyle}
  />
);

export const HubSpotIcon = ({ size = 48 }: IconProps) => (
  <img
    src={hubspotSvg}
    alt="HubSpot"
    width={size}
    height={size}
    draggable={false}
    style={borderStyle}
  />
);

export const JiraIcon = ({ size = 48 }: IconProps) => (
  <img src={jiraPng} alt="Jira" width={size} height={size} draggable={false} style={borderStyle} />
);

export const ConfluenceIcon = ({ size = 48 }: IconProps) => (
  <img
    src={confluencePng}
    alt="Confluence"
    width={size}
    height={size}
    draggable={false}
    style={borderStyle}
  />
);

export const GmailIcon = ({ size = 48 }: IconProps) => (
  <img
    src={gmailPng}
    alt="Gmail"
    width={size}
    height={size}
    draggable={false}
    style={borderStyle}
  />
);

export const AsanaIcon = ({ size = 48 }: IconProps) => (
  <img
    src={asanaPng}
    alt="Asana"
    width={size}
    height={size}
    draggable={false}
    style={borderStyle}
  />
);

export const GongIcon = ({ size = 48 }: IconProps) => (
  <img src={gongPng} alt="Gong" width={size} height={size} draggable={false} style={borderStyle} />
);

export const GranolaIcon = ({ size = 48 }: IconProps) => (
  <img
    src={granolaPng}
    alt="Granola"
    width={size}
    height={size}
    draggable={false}
    style={borderStyle}
  />
);

export const IntercomIcon = ({ size = 48 }: IconProps) => (
  <img
    src={intercomPng}
    alt="Intercom"
    width={size}
    height={size}
    draggable={false}
    style={borderStyle}
  />
);

export const FirefliesIcon = ({ size = 48 }: IconProps) => (
  <img src={firefliesSvg} alt="Fireflies" width={size} height={size} draggable={false} />
);

export const ZendeskIcon = ({ size = 48 }: IconProps) => (
  <img
    src={zendeskPng}
    alt="Zendesk"
    width={size}
    height={size}
    draggable={false}
    style={borderStyle}
  />
);

export const TrelloIcon = ({ size = 48 }: IconProps) => (
  <img
    src={trelloPng}
    alt="Trello"
    width={size}
    height={size}
    draggable={false}
    style={borderStyle}
  />
);

export const GatherIcon = ({ size = 48 }: IconProps) => (
  <img
    src={gatherPng}
    alt="Gather"
    width={size}
    height={size}
    draggable={false}
    style={borderStyle}
  />
);

export const SnowflakeIcon = ({ size = 48 }: IconProps) => (
  <img
    src={snowflakePng}
    alt="Snowflake"
    width={size}
    height={size}
    draggable={false}
    style={borderStyle}
  />
);

export const AttioIcon = ({ size = 48 }: IconProps) => (
  <img
    src={attioSvg}
    alt="Attio"
    width={size}
    height={size}
    draggable={false}
    style={borderStyle}
  />
);

export const CustomDocumentsIcon = ({ size = 48 }: IconProps) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 48 48"
    fill="none"
    style={{ borderRadius: 7.5, border: '0.5px solid rgba(0, 0, 0, 0.1)' }}
  >
    <rect width="48" height="48" rx="8" fill="#6366f1" />
    <path
      d="M16 12h10l8 8v16a2 2 0 01-2 2H16a2 2 0 01-2-2V14a2 2 0 012-2z"
      stroke="white"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      fill="none"
    />
    <path
      d="M26 12v8h8"
      stroke="white"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <path d="M18 28h12M18 24h12M18 32h8" stroke="white" strokeWidth="2" strokeLinecap="round" />
  </svg>
);

export const GitLabIcon = ({ size = 48 }: IconProps) => (
  <img
    src={gitlabSvg}
    alt="GitLab"
    width={size}
    height={size}
    draggable={false}
    style={borderStyle}
  />
);

export const ClickupIcon = ({ size = 48 }: IconProps) => (
  <img src={clickupSvg} alt="ClickUp" width={size} height={size} draggable={false} />
);

export const PylonIcon = ({ size = 48 }: IconProps) => (
  <img
    src={pylonSvg}
    alt="Pylon"
    width={size}
    height={size}
    draggable={false}
    style={borderStyle}
  />
);

export const MondayIcon = ({ size = 48 }: IconProps) => (
  <img
    src={mondaySvg}
    alt="Monday.com"
    width={size}
    height={size}
    draggable={false}
    style={borderStyle}
  />
);

export const PipedriveIcon = ({ size = 48 }: IconProps) => (
  <img
    src={pipedrivePng}
    alt="Pipedrive"
    width={size}
    height={size}
    draggable={false}
    style={borderStyle}
  />
);

export const FigmaIcon = ({ size = 48 }: IconProps) => (
  <img
    src={figmaSvg}
    alt="Figma"
    width={size}
    height={size}
    draggable={false}
    style={borderStyle}
  />
);

export const PostHogIcon = ({ size = 48 }: IconProps) => (
  <img
    src={posthogPng}
    alt="PostHog"
    width={size}
    height={size}
    draggable={false}
    style={borderStyle}
  />
);

export const CanvaIcon = ({ size = 48 }: IconProps) => (
  <img
    src={canvaPng}
    alt="Canva"
    width={size}
    height={size}
    draggable={false}
    style={borderStyle}
  />
);

export const TeamworkIcon = ({ size = 48 }: IconProps) => (
  <img
    src={teamworkSvg}
    alt="Teamwork"
    width={size}
    height={size}
    draggable={false}
    style={borderStyle}
  />
);

interface CheckIconProps {
  strokeWidth?: number;
  size?: number;
  color?: string;
}

export const CheckIcon = ({ strokeWidth = 2, size = 16, color = 'white' }: CheckIconProps) => (
  <svg width={size} height={size} viewBox="0 0 16 16" fill="none">
    <path
      d="M3 8l3 3 7-7"
      stroke={color}
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);
