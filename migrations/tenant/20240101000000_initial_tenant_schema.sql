CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE public.author_authority (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    email text,
    total_slack_characters bigint DEFAULT 0 NOT NULL,
    total_slack_messages bigint DEFAULT 0 NOT NULL,
    top_slack_channels jsonb DEFAULT '[]'::jsonb NOT NULL,
    total_notion_documents bigint DEFAULT 0 NOT NULL,
    total_notion_blocks bigint DEFAULT 0 NOT NULL,
    total_notion_characters bigint DEFAULT 0 NOT NULL,
    linear_issues_created bigint DEFAULT 0 NOT NULL,
    linear_issues_assigned bigint DEFAULT 0 NOT NULL,
    linear_issues_closed bigint DEFAULT 0 NOT NULL,
    linear_issues_comments bigint DEFAULT 0 NOT NULL,
    top_linear_teams jsonb DEFAULT '[]'::jsonb NOT NULL,
    top_linear_labels jsonb DEFAULT '[]'::jsonb NOT NULL,
    source_ids jsonb DEFAULT '[]'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);
ALTER TABLE public.author_authority OWNER TO postgres;
COMMENT ON TABLE public.author_authority IS 'Aggregated author metrics from Slack, Notion, and Linear sources';

COMMENT ON COLUMN public.author_authority.name IS 'Author name';

COMMENT ON COLUMN public.author_authority.email IS 'Author email (primary matching key across systems)';

COMMENT ON COLUMN public.author_authority.total_slack_characters IS 'Total number of characters in all Slack messages';

COMMENT ON COLUMN public.author_authority.total_slack_messages IS 'Total number of Slack messages';

COMMENT ON COLUMN public.author_authority.top_slack_channels IS 'JSON array of top Slack channels: [{channel: "channel_name", total_slack_messages: count, total_slack_characters: count}, ...]';

COMMENT ON COLUMN public.author_authority.total_notion_documents IS 'Total number of Notion documents authored';

COMMENT ON COLUMN public.author_authority.total_notion_blocks IS 'Total number of Notion blocks authored';

COMMENT ON COLUMN public.author_authority.total_notion_characters IS 'Total number of characters in all Notion blocks';

COMMENT ON COLUMN public.author_authority.linear_issues_created IS 'Total number of Linear issues created';

COMMENT ON COLUMN public.author_authority.linear_issues_assigned IS 'Total number of Linear issues assigned';

COMMENT ON COLUMN public.author_authority.linear_issues_closed IS 'Total number of Linear issues closed';

COMMENT ON COLUMN public.author_authority.linear_issues_comments IS 'Total number of Linear comments';

COMMENT ON COLUMN public.author_authority.top_linear_teams IS 'JSON array of top Linear teams with detailed breakdown';

COMMENT ON COLUMN public.author_authority.top_linear_labels IS 'JSON array of top Linear labels with detailed breakdown';

COMMENT ON COLUMN public.author_authority.source_ids IS 'JSON array of source identifiers: [{entity: "slack", entity_id: "user_id"}, {entity: "notion", entity_id: "user_id"}, {entity: "linear", entity_id: "user_id"}]';

CREATE FUNCTION public.merge_author_authority(p_name text, p_email text DEFAULT NULL::text, p_slack_characters bigint DEFAULT NULL::bigint, p_slack_messages bigint DEFAULT NULL::bigint, p_slack_channels jsonb DEFAULT NULL::jsonb, p_notion_documents bigint DEFAULT NULL::bigint, p_notion_blocks bigint DEFAULT NULL::bigint, p_notion_characters bigint DEFAULT NULL::bigint, p_linear_issues_created bigint DEFAULT NULL::bigint, p_linear_issues_assigned bigint DEFAULT NULL::bigint, p_linear_issues_closed bigint DEFAULT NULL::bigint, p_linear_issues_comments bigint DEFAULT NULL::bigint, p_linear_teams jsonb DEFAULT NULL::jsonb, p_linear_labels jsonb DEFAULT NULL::jsonb, p_slack_user_id text DEFAULT NULL::text, p_notion_user_id text DEFAULT NULL::text, p_linear_user_id text DEFAULT NULL::text) RETURNS public.author_authority
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_result "public"."author_authority";
    v_source_ids jsonb;
BEGIN
    
    v_source_ids := '[]'::jsonb;
    
    IF p_slack_user_id IS NOT NULL THEN
        v_source_ids := v_source_ids || jsonb_build_object('entity', 'slack', 'entity_id', p_slack_user_id);
    END IF;
    
    IF p_notion_user_id IS NOT NULL THEN
        v_source_ids := v_source_ids || jsonb_build_object('entity', 'notion', 'entity_id', p_notion_user_id);
    END IF;
    
    IF p_linear_user_id IS NOT NULL THEN
        v_source_ids := v_source_ids || jsonb_build_object('entity', 'linear', 'entity_id', p_linear_user_id);
    END IF;
    
    
    INSERT INTO "public"."author_authority" (
        "name",
        "email",
        "total_slack_characters",
        "total_slack_messages",
        "top_slack_channels",
        "total_notion_documents",
        "total_notion_blocks",
        "total_notion_characters",
        "linear_issues_created",
        "linear_issues_assigned",
        "linear_issues_closed",
        "linear_issues_comments",
        "top_linear_teams",
        "top_linear_labels",
        "source_ids"
    ) VALUES (
        p_name,
        p_email,
        COALESCE(p_slack_characters, 0),
        COALESCE(p_slack_messages, 0),
        COALESCE(p_slack_channels, '[]'::jsonb),
        COALESCE(p_notion_documents, 0),
        COALESCE(p_notion_blocks, 0),
        COALESCE(p_notion_characters, 0),
        COALESCE(p_linear_issues_created, 0),
        COALESCE(p_linear_issues_assigned, 0),
        COALESCE(p_linear_issues_closed, 0),
        COALESCE(p_linear_issues_comments, 0),
        COALESCE(p_linear_teams, '[]'::jsonb),
        COALESCE(p_linear_labels, '[]'::jsonb),
        v_source_ids
    )
    ON CONFLICT (email) DO UPDATE SET
        "name" = COALESCE(p_name, "author_authority"."name"),
        "total_slack_characters" = CASE 
            WHEN p_slack_characters IS NOT NULL THEN p_slack_characters 
            ELSE "author_authority"."total_slack_characters" 
        END,
        "total_slack_messages" = CASE 
            WHEN p_slack_messages IS NOT NULL THEN p_slack_messages 
            ELSE "author_authority"."total_slack_messages" 
        END,
        "top_slack_channels" = CASE 
            WHEN p_slack_channels IS NOT NULL THEN p_slack_channels 
            ELSE "author_authority"."top_slack_channels" 
        END,
        "total_notion_documents" = CASE 
            WHEN p_notion_documents IS NOT NULL THEN p_notion_documents 
            ELSE "author_authority"."total_notion_documents" 
        END,
        "total_notion_blocks" = CASE 
            WHEN p_notion_blocks IS NOT NULL THEN p_notion_blocks 
            ELSE "author_authority"."total_notion_blocks" 
        END,
        "total_notion_characters" = CASE 
            WHEN p_notion_characters IS NOT NULL THEN p_notion_characters 
            ELSE "author_authority"."total_notion_characters" 
        END,
        "linear_issues_created" = CASE
            WHEN p_linear_issues_created IS NOT NULL THEN p_linear_issues_created
            ELSE "author_authority"."linear_issues_created"
        END,
        "linear_issues_assigned" = CASE
            WHEN p_linear_issues_assigned IS NOT NULL THEN p_linear_issues_assigned
            ELSE "author_authority"."linear_issues_assigned"
        END,
        "linear_issues_closed" = CASE
            WHEN p_linear_issues_closed IS NOT NULL THEN p_linear_issues_closed
            ELSE "author_authority"."linear_issues_closed"
        END,
        "linear_issues_comments" = CASE
            WHEN p_linear_issues_comments IS NOT NULL THEN p_linear_issues_comments
            ELSE "author_authority"."linear_issues_comments"
        END,
        "top_linear_teams" = CASE
            WHEN p_linear_teams IS NOT NULL THEN p_linear_teams
            ELSE "author_authority"."top_linear_teams"
        END,
        "top_linear_labels" = CASE
            WHEN p_linear_labels IS NOT NULL THEN p_linear_labels
            ELSE "author_authority"."top_linear_labels"
        END,
        "source_ids" = CASE
            WHEN v_source_ids != '[]'::jsonb THEN 
                
                (
                    SELECT jsonb_agg(DISTINCT elem)
                    FROM (
                        SELECT jsonb_array_elements("author_authority"."source_ids") AS elem
                        UNION
                        SELECT jsonb_array_elements(v_source_ids) AS elem
                    ) AS combined
                )
            ELSE "author_authority"."source_ids"
        END,
        "updated_at" = CURRENT_TIMESTAMP
    RETURNING * INTO v_result;
    
    RETURN v_result;
END;
$$;

ALTER FUNCTION public.merge_author_authority(p_name text, p_email text, p_slack_characters bigint, p_slack_messages bigint, p_slack_channels jsonb, p_notion_documents bigint, p_notion_blocks bigint, p_notion_characters bigint, p_linear_issues_created bigint, p_linear_issues_assigned bigint, p_linear_issues_closed bigint, p_linear_issues_comments bigint, p_linear_teams jsonb, p_linear_labels jsonb, p_slack_user_id text, p_notion_user_id text, p_linear_user_id text) OWNER TO postgres;

CREATE FUNCTION public.update_updated_at_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;

ALTER FUNCTION public.update_updated_at_column() OWNER TO postgres;

CREATE TABLE public.chunks (
    id character varying(64) NOT NULL,
    document_id character varying(255) NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    content text NOT NULL,
    embedding halfvec(3072) NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    authority_multiplier numeric DEFAULT 0.0
);

ALTER TABLE public.chunks OWNER TO postgres;

COMMENT ON COLUMN public.chunks.authority_multiplier IS 'Score for search relevance based on authority (0.0 = default, higher = more relevant)';

CREATE TABLE public.config (
    key character varying(255) NOT NULL,
    value text NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);

ALTER TABLE public.config OWNER TO postgres;

CREATE TABLE public.documents (
    id character varying(255) NOT NULL,
    content_hash character varying(64) NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    source character varying(255) NOT NULL,
    source_created_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    annotations text DEFAULT ''::text NOT NULL,
    annotation_reviewed_at timestamp with time zone,
    content text,
    source_updated_at timestamp with time zone
);

ALTER TABLE public.documents OWNER TO postgres;

CREATE TABLE public.exclusion_rules (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    entity_type character varying(50) NOT NULL,
    rule jsonb NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);

ALTER TABLE public.exclusion_rules OWNER TO postgres;

CREATE TABLE public.ingest_artifact (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    entity text NOT NULL,
    entity_id text NOT NULL,
    ingest_job_id uuid NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    source_updated_at timestamp with time zone NOT NULL,
    content jsonb DEFAULT '{}'::jsonb NOT NULL,
    indexed_at timestamp with time zone
);

ALTER TABLE public.ingest_artifact OWNER TO postgres;

COMMENT ON COLUMN public.ingest_artifact.ingest_job_id IS 'Reference to ingest_job.id. No foreign key constraint to allow job cleanup without losing artifacts.';

CREATE TABLE public.sitemap (
    id character varying(255) NOT NULL,
    name text NOT NULL,
    external_id character varying(255) NOT NULL,
    source character varying(255) NOT NULL,
    purpose text,
    main_contributors text[],
    relevant_for text,
    not_relevant_for text,
    active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);

ALTER TABLE public.sitemap OWNER TO postgres;

CREATE TABLE public.slack_message_reactions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    message_id text NOT NULL,
    channel_id text NOT NULL,
    user_id text NOT NULL,
    reaction text NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);

ALTER TABLE public.slack_message_reactions OWNER TO postgres;

CREATE TABLE public.slack_messages (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    message_id text NOT NULL,
    channel_id text NOT NULL,
    user_id text NOT NULL,
    question text NOT NULL,
    answer text NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);

ALTER TABLE public.slack_messages OWNER TO postgres;

ALTER TABLE ONLY public.author_authority
    ADD CONSTRAINT author_authority_email_key UNIQUE (email);

ALTER TABLE ONLY public.author_authority
    ADD CONSTRAINT author_authority_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.chunks
    ADD CONSTRAINT chunks_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.config
    ADD CONSTRAINT config_pkey PRIMARY KEY (key);

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_content_hash_key UNIQUE (content_hash);

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.exclusion_rules
    ADD CONSTRAINT exclusion_rules_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.ingest_artifact
    ADD CONSTRAINT ingest_artifact_pkey PRIMARY KEY (id);


ALTER TABLE ONLY public.sitemap
    ADD CONSTRAINT sitemap_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.sitemap
    ADD CONSTRAINT sitemap_source_external_id_key UNIQUE (source, external_id);

ALTER TABLE ONLY public.slack_message_reactions
    ADD CONSTRAINT slack_message_reactions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.slack_message_reactions
    ADD CONSTRAINT slack_message_reactions_unique_user_message_reaction UNIQUE (message_id, user_id, reaction);

ALTER TABLE ONLY public.slack_messages
    ADD CONSTRAINT slack_messages_message_id_key UNIQUE (message_id);

ALTER TABLE ONLY public.slack_messages
    ADD CONSTRAINT slack_messages_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.ingest_artifact
    ADD CONSTRAINT unique_entity_entity_id UNIQUE (entity, entity_id);

CREATE INDEX idx_author_authority_email ON public.author_authority USING btree (email);

CREATE INDEX idx_author_authority_linear_issues_created ON public.author_authority USING btree (linear_issues_created DESC);

CREATE INDEX idx_author_authority_name ON public.author_authority USING btree (name);

CREATE INDEX idx_author_authority_source_ids ON public.author_authority USING gin (source_ids);

CREATE INDEX idx_author_authority_total_notion_documents ON public.author_authority USING btree (total_notion_documents DESC);

CREATE INDEX idx_author_authority_total_slack_messages ON public.author_authority USING btree (total_slack_messages DESC);

CREATE INDEX idx_author_authority_updated_at ON public.author_authority USING btree (updated_at);

CREATE INDEX idx_chunks_authority_multiplier ON public.chunks USING btree (authority_multiplier DESC);

CREATE INDEX idx_chunks_document_id ON public.chunks USING btree (document_id);

CREATE INDEX idx_chunks_embedding_cosine ON public.chunks USING hnsw (embedding public.halfvec_cosine_ops);

CREATE INDEX idx_documents_annotation_stale_review ON public.documents USING btree (annotation_reviewed_at, annotations) WHERE (annotations <> ''::text);

CREATE INDEX idx_documents_annotations ON public.documents USING btree (annotations) WHERE (annotations <> ''::text);

CREATE INDEX idx_documents_metadata ON public.documents USING gin (metadata);

CREATE INDEX idx_documents_source ON public.documents USING btree (source);

CREATE INDEX idx_documents_source_created_at ON public.documents USING btree (source_created_at);

CREATE INDEX idx_documents_source_updated_at ON public.documents USING btree (source_updated_at);

CREATE INDEX idx_documents_updated_at ON public.documents USING btree (updated_at);

CREATE INDEX idx_exclusion_rules_active ON public.exclusion_rules USING btree (is_active) WHERE (is_active = true);

CREATE INDEX idx_exclusion_rules_entity_type ON public.exclusion_rules USING btree (entity_type);

CREATE INDEX idx_ingest_artifact_content ON public.ingest_artifact USING gin (content);

CREATE INDEX idx_ingest_artifact_entity ON public.ingest_artifact USING btree (entity);

CREATE INDEX idx_ingest_artifact_entity_entity_id ON public.ingest_artifact USING btree (entity, entity_id);

CREATE INDEX idx_ingest_artifact_entity_id ON public.ingest_artifact USING btree (entity_id);

CREATE INDEX idx_ingest_artifact_source_updated_at ON public.ingest_artifact USING btree (source_updated_at);

CREATE INDEX idx_ingest_artifact_indexed_at ON public.ingest_artifact USING btree (indexed_at);

CREATE INDEX idx_ingest_artifact_ingest_job_id ON public.ingest_artifact USING btree (ingest_job_id);

CREATE INDEX idx_sitemap_active ON public.sitemap USING btree (active);

CREATE INDEX idx_sitemap_external_id ON public.sitemap USING btree (external_id);

CREATE INDEX idx_sitemap_source ON public.sitemap USING btree (source);

CREATE INDEX idx_slack_channel_id ON public.ingest_artifact USING btree (((metadata ->> 'channel_id'::text))) WHERE ((entity = 'slack_message'::text) AND ((metadata ->> 'channel_id'::text) IS NOT NULL));

CREATE INDEX idx_slack_message_reactions_channel_id ON public.slack_message_reactions USING btree (channel_id);

CREATE INDEX idx_slack_message_reactions_created_at ON public.slack_message_reactions USING btree (created_at);

CREATE INDEX idx_slack_message_reactions_message_id ON public.slack_message_reactions USING btree (message_id);

CREATE INDEX idx_slack_message_reactions_reaction ON public.slack_message_reactions USING btree (reaction);

CREATE INDEX idx_slack_message_reactions_user_id ON public.slack_message_reactions USING btree (user_id);

CREATE INDEX idx_slack_message_ts ON public.ingest_artifact USING btree (((content ->> 'ts'::text))) WHERE ((entity = 'slack_message'::text) AND ((content ->> 'ts'::text) IS NOT NULL));

CREATE INDEX idx_slack_messages_channel_id ON public.slack_messages USING btree (channel_id);

CREATE INDEX idx_slack_messages_created_at ON public.slack_messages USING btree (created_at);

CREATE INDEX idx_slack_messages_message_id ON public.slack_messages USING btree (message_id);

CREATE INDEX idx_slack_messages_user_id ON public.slack_messages USING btree (user_id);

CREATE INDEX idx_slack_thread_lookup ON public.ingest_artifact USING btree (((content ->> 'thread_ts'::text))) WHERE ((entity = 'slack_message'::text) AND ((content ->> 'thread_ts'::text) IS NOT NULL));

CREATE INDEX idx_slack_ts ON public.ingest_artifact USING btree ((((content ->> 'ts'::text))::double precision)) WHERE ((entity = 'slack_message'::text) AND ((content ->> 'ts'::text) IS NOT NULL));

CREATE TRIGGER update_author_authority_updated_at BEFORE UPDATE ON public.author_authority FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

CREATE TRIGGER update_chunks_updated_at BEFORE UPDATE ON public.chunks FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

CREATE TRIGGER update_config_updated_at BEFORE UPDATE ON public.config FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

CREATE TRIGGER update_documents_updated_at BEFORE UPDATE ON public.documents FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

CREATE TRIGGER update_exclusion_rules_updated_at BEFORE UPDATE ON public.exclusion_rules FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

CREATE TRIGGER update_sitemap_updated_at BEFORE UPDATE ON public.sitemap FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

ALTER TABLE ONLY public.chunks
    ADD CONSTRAINT fk_chunks_document FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;
