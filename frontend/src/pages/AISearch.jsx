import React, { useState, useRef, useEffect } from 'react'
import { useConfig } from '../configContext'
import axios from '../axios'

const AISearch = () => {
    const config = useConfig()
    const [query, setQuery] = useState('')
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState('')
    const [chatHistory, setChatHistory] = useState([])
    const chatEndRef = useRef(null)

    useEffect(() => {
        chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }, [chatHistory])

    const handleSubmit = async (e) => {
        e.preventDefault()
        const trimmed = query.trim()
        if (!trimmed || loading) return

        const userMessage = { role: 'user', content: trimmed, isHtml: false }
        setChatHistory(prev => [...prev, userMessage])
        setQuery('')
        setLoading(true)
        setError('')

        try {
            const res = await axios.post(`${config.API_BASE_URL}ai/search`, { query: trimmed })
            const answer = res.data?.search || 'No response received.'
            const assistantMessage = { role: 'assistant', content: answer, isHtml: true }
            setChatHistory(prev => [...prev, assistantMessage])
        } catch (err) {
            const errMsg = err?.response?.data?.detail || err.message || 'Request failed'
            setError(errMsg)
            setChatHistory(prev => [...prev, { role: 'assistant', content: `Error: ${errMsg}`, isHtml: false }])
        } finally {
            setLoading(false)
        }
    }

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            handleSubmit(e)
        }
    }

    const clearChat = () => {
        setChatHistory([])
        setError('')
    }

    return (
        <div className='container-fluid p-3 d-flex flex-column' style={{ height: 'calc(100vh - 32px)' }}>
            <style>{`
                .chat-answer h3 { font-size: 1.1rem; margin: 0.5rem 0 0.3rem; }
                .chat-answer p { margin: 0.3rem 0; }
                .chat-answer ul, .chat-answer ol { margin: 0.3rem 0; padding-left: 1.5rem; }
                .chat-answer li { margin: 0.2rem 0; }
                .chat-answer code { background: #e9ecef; padding: 0.15rem 0.35rem; border-radius: 3px; font-size: 0.9em; }
                .chat-answer pre { background: #2d2d2d; color: #f8f8f2; padding: 0.75rem; border-radius: 6px; overflow-x: auto; margin: 0.5rem 0; }
                .chat-answer pre code { background: none; color: inherit; padding: 0; }
                .chat-answer blockquote { border-left: 3px solid #6c757d; margin: 0.5rem 0; padding: 0.25rem 0.75rem; color: #495057; }
                .chat-answer a { color: #0d6efd; text-decoration: none; }
                .chat-answer a:hover { text-decoration: underline; }
                .chat-answer strong { font-weight: 600; }
                .chat-answer h3:not(:first-child) { margin-top: 1rem; }
            `}</style>
            <div className='d-flex justify-content-between align-items-center mb-3'>
                <h3 className='m-0'>Search Assistant</h3>
                <button className='btn btn-sm btn-outline-secondary' onClick={clearChat} disabled={loading}>
                    Clear Chat
                </button>
            </div>

            <p className='text-muted mb-3' style={{ fontSize: '0.9rem' }}>
                AI-powered search using LangGraph. Ask any question and get real-time answers from the web.
            </p>

            {/* Chat area */}
            <div className='flex-grow-1 overflow-auto border rounded p-3 mb-3' style={{ background: '#f8f9fa', minHeight: 200 }}>
                {chatHistory.length === 0 && (
                    <div className='text-center text-muted py-5'>
                        <div style={{ fontSize: '2rem' }}>&#x1F50D;</div>
                        <div className='mt-2'>Ask a question to start searching</div>
                        <div style={{ fontSize: '0.85rem' }} className='mt-1'>
                            Try: "What are the latest trends in AI?" or "How does YOLOv8 work?"
                        </div>
                    </div>
                )}

                {chatHistory.map((msg, idx) => (
                    <div key={idx} className={`d-flex mb-3 ${msg.role === 'user' ? 'justify-content-end' : 'justify-content-start'}`}>
                        {msg.isHtml ? (
                            <div
                                className={`rounded p-3 bg-white border chat-answer`}
                                style={{ maxWidth: '75%', wordBreak: 'break-word' }}
                                dangerouslySetInnerHTML={{ __html: msg.content }}
                            />
                        ) : (
                            <div
                                className={`rounded p-3 ${msg.role === 'user' ? 'bg-primary text-white' : 'bg-white border'}`}
                                style={{ maxWidth: '75%', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}
                            >
                                {msg.content}
                            </div>
                        )}
                    </div>
                ))}

                {loading && (
                    <div className='d-flex justify-content-start mb-3'>
                        <div className='bg-white border rounded p-3'>
                            <span className='text-muted'>Searching...</span>
                        </div>
                    </div>
                )}

                <div ref={chatEndRef} />
            </div>

            {/* Input area */}
            <form onSubmit={handleSubmit} className='d-flex gap-2'>
                <textarea
                    className='form-control'
                    placeholder='Type your question here...'
                    value={query}
                    onChange={e => setQuery(e.target.value)}
                    onKeyDown={handleKeyDown}
                    disabled={loading}
                    rows={1}
                    style={{ resize: 'none' }}
                />
                <button
                    type='submit'
                    className='btn btn-primary px-4'
                    disabled={loading || !query.trim()}
                >
                    {loading ? 'Searching...' : 'Search'}
                </button>
            </form>
        </div>
    )
}

export default AISearch
