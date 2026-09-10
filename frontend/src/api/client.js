import axios from 'axios'

const client = axios.create({
  baseURL: 'https://bureaucracy-navigator.onrender.com',
  timeout: 60000, // Render's free tier can take 30-50s to cold-start; give it room
})

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Render's free tier spins the backend down after ~15 minutes idle. The first request
// after that hits Render's own gateway (not our FastAPI app) and times out with NO CORS
// headers at all, because our app's CORSMiddleware never got a chance to run. The browser
// reports that as a generic "Network Error" / CORS failure -- there's no HTTP status code
// to tell it apart from a real outage. So: retry once after a short delay. If it was a
// cold start, the retry succeeds once the container is up. If it's a real outage, the
// retry fails too and we surface a clear message instead of a confusing raw CORS error.
client.interceptors.response.use(
  (response) => response,
  async (error) => {
    const config = error.config
    const isNetworkError = error.code === 'ERR_NETWORK' || error.message === 'Network Error'

    if (isNetworkError && config && !config.__retriedAfterColdStart) {
      config.__retriedAfterColdStart = true
      await new Promise((resolve) => setTimeout(resolve, 5000))
      return client(config)
    }

    if (isNetworkError) {
      error.message =
        'Could not reach the server -- it may be waking up after being idle. Please try again in a moment.'
    }

    return Promise.reject(error)
  }
)

export default client
