export interface JobAccepted {
  jobId: string
}

export interface JobProcessing {
  jobId: string
  status: 'processing'
  stage?: 'analyzing' | 'extracting' | 'composing' | 'finalizing'
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

export type JobStatusResponse = JobProcessing | JobCompleted | JobFailed