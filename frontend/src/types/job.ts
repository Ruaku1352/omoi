/** processing 中の処理段階。contracts/job-status-response.schema.json が正本。 */
export type JobStage = 'analyzing' | 'extracting' | 'composing' | 'finalizing'
export interface JobAccepted {
  jobId: string
}

export interface JobPending {
  jobId: string
  status: 'pending'
}

export interface JobProcessing {
  jobId: string
  status: 'processing'
  stage?: JobStage
}

export interface JobCompleted {
  jobId: string
  status: 'completed'
  result: {
    artwork: import('./artwork').Artwork
    assetManifest: import('./assetManifest').AssetManifest
  }
}

export interface JobFailed {
  jobId: string
  status: 'failed'
  error: {
    code: string
    message: string
    retryable: boolean
    details: unknown
  }
}

export type JobStatusResponse = JobPending | JobProcessing | JobCompleted | JobFailed
