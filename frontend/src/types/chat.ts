/** Types matching the backend API models. */

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  traceSteps?: TraceStep[]
  citations?: Citation[]
  feedbackS3Key?: string | null
  feedbackTimestamp?: string | null
}

export interface TraceStep {
  label: string
  detail?: string
}

export interface Citation {
  source: string
  text: string
}

export interface TextDoc {
  name: string
  page_count: number
  context: string
  context_mode: string
}

export interface CodeInterpreterDoc {
  name: string
  media_type: string
}

export interface DocumentUploadResponse {
  text_docs: TextDoc[]
  code_interpreter_docs: CodeInterpreterDoc[]
  errors: { name: string; error: string }[]
}

export interface FeedbackPayload {
  session_id: string
  message_index: number
  rating: 'positive' | 'negative' | null
  user_query: string
  agent_response: string
  agent_variant: string
  comment?: string
  retrieved_chunks?: { text: string; source: string }[]
  tools_used?: string[]
  s3_key_override?: string | null
  original_timestamp?: string | null
}

export interface SourceMetadata {
  filename: string
  bucket: string
  type: 'website' | 'fedlex' | 'document'
  source_url?: string
  fedlex_url?: string
  title?: string
  abbreviation?: string
}
