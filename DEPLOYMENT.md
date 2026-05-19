# Deployment Guide

This guide covers deploying CloudDash to production using Render (backend) and Vercel (frontend).

---

## Backend Deployment (Render)

### Prerequisites
- GitHub repository with the CloudDash code
- Render account (free tier)
- API keys for:
  - Google Gemini (or other LLM provider)
  - Cohere (for reranking)
  - Tavily (for web search)
  - Sarvam AI (optional, for multilingual)
  - LangSmith (optional, for tracing)

### Steps

1. **Push code to GitHub**
   ```bash
   git add .
   git commit -m "Ready for deployment"
   git push origin main
   ```

2. **Create new Render service**
   - Go to [render.com](https://render.com)
   - Click "New +" → "Web Service"
   - Connect your GitHub repository
   - Render will auto-detect the `render.yaml` blueprint

3. **Configure environment variables** (in Render dashboard)
   - `GOOGLE_API_KEY` — Your Gemini API key
   - `COHERE_API_KEY` — Your Cohere API key
   - `TAVILY_API_KEY` — Your Tavily API key
   - `SARVAM_API_KEY` — Your Sarvam API key (optional)
   - `LANGCHAIN_API_KEY` — Your LangSmith API key (optional)
   - `LANGCHAIN_TRACING_V2` — Set to `true` to enable tracing

4. **Deploy**
   - Click "Create Web Service"
   - Render will build and deploy automatically
   - First build takes ~5-10 minutes (ChromaDB ingest)

5. **Get your backend URL**
   - Render will provide a URL like `https://clouddash-api.onrender.com`
   - Save this for frontend configuration

---

## Frontend Deployment (Vercel)

### Prerequisites
- Vercel account (free tier)
- Backend URL from Render deployment

### Steps

1. **Push frontend code to GitHub**
   - The `frontend/` directory should be in your repository

2. **Create new Vercel project**
   - Go to [vercel.com](https://vercel.com)
   - Click "Add New..." → "Project"
   - Import your GitHub repository
   - Set root directory to `frontend`

3. **Configure environment variables**
   - `NEXT_PUBLIC_API_URL` — Your backend URL from Render (e.g., `https://clouddash-api.onrender.com`)

4. **Deploy**
   - Click "Deploy"
   - Vercel will build and deploy automatically
   - Takes ~2-3 minutes

5. **Get your frontend URL**
   - Vercel will provide a URL like `https://clouddash-frontend.vercel.app`

---

## Post-Deployment Checklist

- [ ] Backend health check: `https://<backend-url>/api/health`
- [ ] Frontend loads and connects to backend
- [ ] Test a simple chat message
- [ ] Test agent routing (try "I need help with billing")
- [ ] Test CRAG retrieval (try "How do I set up alerts?")
- [ ] Test HITL escalation (try "This is urgent, escalate to human")
- [ ] Check LangSmith traces (if enabled)

---

## Local Development

### Backend
```bash
cd backend
# Install dependencies
pip install -e .
# Ingest knowledge base
python -m clouddash.scripts.ingest_kb
# Run server
uvicorn clouddash.api.app:app --host 0.0.0.0 --port 8001 --reload
```

### Frontend
```bash
cd frontend
# Install dependencies
npm install
# Run dev server
npm run dev
# Frontend runs on http://localhost:3003
```

---

## Troubleshooting

**Backend fails to start on Render**
- Check Render logs for errors
- Ensure all environment variables are set
- ChromaDB ingest may take time on first deploy

**Frontend can't connect to backend**
- Verify `NEXT_PUBLIC_API_URL` is set correctly in Vercel
- Check backend health endpoint
- Ensure CORS is configured (backend allows all origins in dev)

**SSE streaming not working**
- Verify backend is running and accessible
- Check browser console for network errors
- Ensure no proxy is blocking SSE connections

**LLM provider errors**
- Check API keys are valid
- Verify provider is supported (Google, Sarvam, Groq, NVIDIA)
- Check rate limits and quotas

---

## Cost Estimate

### Render (Backend)
- Free tier: 512MB RAM, 0.1 CPU
- Cost: $0/month
- Limitations: Cold starts (~30s), 750 hours/month

### Vercel (Frontend)
- Free tier: Unlimited bandwidth, 100GB-hosted data
- Cost: $0/month
- Limitations: 100GB bandwidth, 6,000 minutes execution

### API Costs (estimated)
- Google Gemini: Free tier (15 RPM, 1M tokens/day)
- Cohere Rerank: ~$0.001/1K calls
- Tavily Search: Free tier (1000 searches/month)
- LangSmith: Free tier (limited traces)

**Total estimated cost: $0/month for development/testing**

---

## Security Notes

- Never commit `.env` files
- Use environment variables in production
- Rotate API keys regularly
- Enable rate limiting on API endpoints
- Use HTTPS only (Render and Vercel provide this automatically)
