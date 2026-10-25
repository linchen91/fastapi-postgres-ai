import React, { useState } from 'react'
import { useConfig } from '../configContext'
import axios from '../axios'

// Same formats the backend accepts (.sql is excluded: it only runs on the console)
const ACCEPT = '.csv,.tsv,.xls,.xlsx,.json,.jsonl,.ndjson,.parquet,.feather,.xml,.html,.htm,.pbix'

const DataAnalysis = () => {
    const config = useConfig()
    const [file, setFile] = useState(null)
    const [loading, setLoading] = useState(false)
    const [deepLoading, setDeepLoading] = useState(false)
    const [error, setError] = useState('')
    const [reportHtml, setReportHtml] = useState('')
    // 'normal' | 'deep' — highlights which analyze button was last clicked
    const [activeMode, setActiveMode] = useState('')

    const handleFileChange = (e) => {
        setFile(e.target.files?.[0] || null)
        setError('')
    }

    const handleUpload = async (deep = false) => {
        if (!file || loading) return

        setLoading(true)
        setDeepLoading(deep)
        setActiveMode(deep ? 'deep' : 'normal')
        setError('')
        setReportHtml('')

        const form = new FormData()
        form.append('file', file)

        try {
            const endpoint = deep ? 'ai/data/deep' : 'ai/data'
            const res = await axios.post(`${config.API_BASE_URL}${endpoint}`, form)
            const html = res.data?.html
            if (!html) throw new Error('No report HTML returned')
            setReportHtml(html)
        } catch (err) {
            setError(err?.response?.data?.detail || err.message || 'Request failed')
        } finally {
            setLoading(false)
            setDeepLoading(false)
        }
    }

    const handleClear = () => {
        setFile(null)
        setReportHtml('')
        setError('')
        setActiveMode('')
    }

    return (
        <div className='container-fluid p-3'>
            <h3 className='mb-3'>Data Analysis</h3>

            <p className='text-muted' style={{ fontSize: '0.9rem' }}>
                Upload a data file and get an AI-generated chart and analysis report, powered by LangGraph.
                Large files can take a minute.
            </p>

            {/* Upload area */}
            <div className='d-flex gap-2 align-items-center mb-3 flex-wrap'>
                <input
                    type='file'
                    className='form-control'
                    style={{ maxWidth: '420px' }}
                    accept={ACCEPT}
                    onChange={handleFileChange}
                    disabled={loading}
                />
                <button
                    className={`btn px-4 ${activeMode === 'normal' ? 'btn-primary' : 'btn-outline-primary'}`}
                    onClick={() => handleUpload(false)}
                    disabled={loading || !file}
                >
                    {loading && !deepLoading ? 'Analyzing...' : 'Analyze'}
                </button>
                <button
                    className={`btn px-4 ${activeMode === 'deep' ? 'btn-primary' : 'btn-outline-primary'}`}
                    onClick={() => handleUpload(true)}
                    disabled={loading || !file}
                >
                    {loading && deepLoading ? 'Deep analyzing...' : 'Deep Analyze'}
                </button>
                {file && !loading && (
                    <button className='btn btn-outline-secondary' onClick={handleClear}>
                        Clear
                    </button>
                )}
            </div>

            {error && <div className='alert alert-danger py-2'>{error}</div>}

            {/* Result area */}
            {loading && (
                <div className='border rounded p-5 text-center text-muted' style={{ background: '#f8f9fa' }}>
                    <div style={{ fontSize: '2rem' }}>&#x1F9EA;</div>
                    <div className='mt-2'>
                        {deepLoading ? 'Deep analyzing' : 'Analyzing'} "{file?.name}" ... please wait
                    </div>
                </div>
            )}

            {!loading && !reportHtml && !error && (
                <div className='border rounded p-5 text-center text-muted' style={{ background: '#f8f9fa' }}>
                    <div style={{ fontSize: '2rem' }}>&#x1F4CA;</div>
                    <div className='mt-2'>Upload a file to generate a chart and analysis report</div>
                </div>
            )}

            {!loading && reportHtml && (
                <iframe
                    title='Data Analysis Report'
                    className='border rounded w-100'
                    srcDoc={reportHtml}
                    style={{ height: 'calc(100vh - 260px)' }}
                />
            )}
        </div>
    )
}

export default DataAnalysis
