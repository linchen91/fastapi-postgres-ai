import React, { useState } from 'react'
import { useConfig } from '../configContext'
import axios from '../axios'
import { Modal } from 'bootstrap'

const AiSummary = ({ stats }) => {
    const config = useConfig();
    const [content, setContent] = useState('');
    const [loading, setLoading] = useState(false);

    const showModal = () => {
        const modalElement = document.getElementById('aiSummaryModal');
        if (!modalElement) return;
        const modal = new Modal(modalElement);
        modal.show();
    };

    const callSummary = async () => {
        const token = localStorage.getItem('token') || '';
        setLoading(true);
        try {
            const response = await axios.post(`${config.API_BASE_URL}ai/summary`, 
                { stats },
                {
                    headers: {
                        Accept: 'application/json',
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    },
                }
            );
            const data = response.data;
            let text = typeof data === 'string' ? data
                : data?.message || data?.summary || data?.ai || data?.text ||
                JSON.stringify(data, null, 2) || 'No summary available.';
            setContent(text || 'No summary available.');
            showModal();
        } catch (error) {
            const errorMessage = error?.response?.data
                ? typeof error.response.data === 'string'
                    ? error.response.data
                    : JSON.stringify(error.response.data)
                : error?.message;
            setContent(`Error: ${errorMessage}`);
            showModal();
        } finally {
            setLoading(false);
        }
    };

    return (
        <div>
            <button className="btn btn-dark" onClick={callSummary} disabled={loading}>
                {loading ? 'Generating Summary...' : 'Generate AI Summary'}
            </button>

            <div className="modal fade" id="aiSummaryModal" tabIndex="-1" aria-hidden="true">
                <div className="modal-dialog modal-dialog-centered modal-lg">
                    <div className="modal-content">
                        <div className="modal-header">
                            <h5 className="modal-title">AI Summary</h5>
                            <button type="button" className="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div className="modal-body" style={{ whiteSpace: 'pre-wrap', wordWrap: 'break-word', fontSize: '14px', textAlign: 'left' }}>
                            {content}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    )
};

export default AiSummary;
