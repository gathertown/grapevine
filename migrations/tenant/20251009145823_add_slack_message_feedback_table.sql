-- Add feedback button tracking table
-- This table stores user feedback from interactive Slack buttons (not emoji reactions)

CREATE TABLE public.slack_message_feedback (
    id UUID DEFAULT gen_random_uuid() NOT NULL,
    message_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    feedback_type TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT slack_message_feedback_pkey PRIMARY KEY (id),
    CONSTRAINT slack_message_feedback_feedback_type_check CHECK (feedback_type IN ('positive', 'negative')),
    CONSTRAINT slack_message_feedback_unique_user_message_feedback UNIQUE (message_id, user_id)
);

ALTER TABLE public.slack_message_feedback OWNER TO postgres;

-- Indexes for performance
CREATE INDEX idx_slack_message_feedback_message_id ON public.slack_message_feedback USING btree (message_id);
CREATE INDEX idx_slack_message_feedback_channel_id ON public.slack_message_feedback USING btree (channel_id);
CREATE INDEX idx_slack_message_feedback_created_at ON public.slack_message_feedback USING btree (created_at);
CREATE INDEX idx_slack_message_feedback_user_id ON public.slack_message_feedback USING btree (user_id);

-- Comments for documentation
COMMENT ON TABLE public.slack_message_feedback IS 'Tracks user feedback via Slack interactive buttons (not emoji reactions)';
COMMENT ON COLUMN public.slack_message_feedback.message_id IS 'Bot response message timestamp';
COMMENT ON COLUMN public.slack_message_feedback.channel_id IS 'Slack channel ID where the message was posted';
COMMENT ON COLUMN public.slack_message_feedback.user_id IS 'Slack user ID who provided feedback';
COMMENT ON COLUMN public.slack_message_feedback.feedback_type IS 'User feedback: positive or negative';
