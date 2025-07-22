import { useState, useEffect } from 'react'
import './App.css'

// Dark Professional Design System (inspired by portfolio)
const colors = {
  primary: '#ffffff',      // Pure white for primary actions
  primaryLight: '#f8f9fa', // Light grey for hover states
  primaryDark: '#e9ecef',  // Slightly darker white
  
  background: '#2c2c2c',   // Dark charcoal background
  surface: '#3a3a3a',     // Slightly lighter dark grey
  surfaceLight: '#4a4a4a', // Even lighter for cards/sections
  
  textPrimary: '#ffffff',  // Pure white text
  textSecondary: '#e0e0e0', // Light grey text
  textMuted: '#b0b0b0',    // Muted light grey
  
  positive: '#ffffff',     // White for positive
  negative: '#cccccc',     // Light grey for negative
  neutral: '#aaaaaa',      // Medium grey for neutral
  
  accent: '#ffffff',       // White accent
  border: '#4a4a4a',       // Dark border
  
  gradient: 'linear-gradient(135deg, #2c2c2c 0%, #3a3a3a 100%)'
}

interface SearchResult {
  ticker: string
  found: boolean
  ticker_info: {
    ticker: string
    total_mentions: number
    avg_sentiment: number
    sentiment_volatility: number
    first_mention: string
    last_mention: string
    min_sentiment: number
    max_sentiment: number
  } | null
  timeline: Array<{
    date: string
    mentions: number
    avg_sentiment: number
    sentiment_volatility: number
    min_sentiment: number
    max_sentiment: number
  }>
  recent_posts: Array<{
    reddit_id: string
    score: number
    pos_prob: number
    neg_prob: number
    scored_ts: string
    reddit_url: string
  }>
  search_params: {
    days: number
    limit: number
  }
}

interface TrendingTicker {
  ticker: string
  mention_count: number
  avg_sentiment: number
  sentiment_volatility: number
  min_sentiment: number
  max_sentiment: number
  last_seen: string
}

interface AutocompleteSuggestion {
  ticker: string
  mention_count: number
  last_seen: string
  avg_sentiment: number
}

function App() {
  // Search state
  const [currentView, setCurrentView] = useState<'search' | 'trending'>('search')
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResult, setSearchResult] = useState<SearchResult | null>(null)
  const [searchLoading, setSearchLoading] = useState(false)
  
  // Trending state
  const [trendingData, setTrendingData] = useState<{
    daily: TrendingTicker[]
    weekly: TrendingTicker[]
    monthly: TrendingTicker[]
  }>({ daily: [], weekly: [], monthly: [] })
  const [trendingLoading, setTrendingLoading] = useState(false)
  
  // Autocomplete state
  const [autocompleteResults, setAutocompleteResults] = useState<AutocompleteSuggestion[]>([])
  const [showAutocomplete, setShowAutocomplete] = useState(false)
  
  // Load trending data on component mount
  useEffect(() => {
    loadTrendingData()
  }, [])

  const handleSearch = async (ticker: string) => {
    console.log('handleSearch called with ticker:', ticker)
    if (!ticker.trim()) {
      console.log('Empty ticker, returning early')
      return
    }
    
    console.log('Starting search for:', ticker)
    setSearchLoading(true)
    setCurrentView('search')
    
    try {
      const response = await fetch(`/api/search/${ticker.toUpperCase()}`)
      const data = await response.json()
      console.log('Search response:', data)
      setSearchResult(data)
      console.log('searchResult set to:', data)
    } catch (error) {
      console.error('Search failed:', error)
      setSearchResult(null)
    } finally {
      setSearchLoading(false)
      console.log('Search loading set to false')
    }
  }

  const loadTrendingData = async () => {
    setTrendingLoading(true)
    try {
      const [dailyRes, weeklyRes, monthlyRes] = await Promise.all([
        fetch('/api/trending?period=24h&limit=10'),
        fetch('/api/trending?period=7d&limit=10'),
        fetch('/api/trending?period=30d&limit=10')
      ])
      
      const daily = await dailyRes.json()
      const weekly = await weeklyRes.json()
      const monthly = await monthlyRes.json()
      
      setTrendingData({
        daily: daily.tickers || [],
        weekly: weekly.tickers || [],
        monthly: monthly.tickers || []
      })
    } catch (error) {
      console.error('Failed to load trending data:', error)
    } finally {
      setTrendingLoading(false)
    }
  }

  const handleAutocomplete = async (query: string) => {
    if (query.length < 2) {
      setAutocompleteResults([])
      setShowAutocomplete(false)
      return
    }
    
    try {
      const response = await fetch(`/api/autocomplete?q=${query}&limit=8`)
      const data = await response.json()
      setAutocompleteResults(data.suggestions || [])
      setShowAutocomplete(true)
    } catch (error) {
      console.error('Autocomplete failed:', error)
      setAutocompleteResults([])
    }
  }

  const getSentimentLabel = (score: number) => {
    if (score > 0.1) return 'positive'
    if (score < -0.1) return 'negative'
    return 'neutral'
  }

  const getSentimentColor = (score: number) => {
    if (score > 0.1) return colors.positive
    if (score < -0.1) return colors.negative
    return colors.neutral
  }

  const getSentimentSymbol = (score: number) => {
    if (score > 0.1) return '▲'  // Triangle up for positive
    if (score < -0.1) return '▼'  // Triangle down for negative
    return '●'  // Circle for neutral
  }

  if (searchLoading || trendingLoading) {
    return (
      <div style={{
        minHeight: '100vh',
        background: colors.background,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: colors.textPrimary
      }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ 
            fontSize: '3rem', 
            marginBottom: '1rem',
            color: colors.textSecondary
          }}>●</div>
          <div style={{ fontSize: '1.25rem', fontWeight: '600' }}>
            {searchLoading ? 'Searching...' : 'Loading trending data...'}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div style={{
      minHeight: '100vh',
      height: '100vh',
      width: '100vw',
      background: colors.background,
      color: colors.textPrimary,
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif',
      margin: 0,
      padding: 0,
      overflow: 'auto'
    }}>
      {/* Hero Section with Search */}
      <div style={{
        background: colors.gradient,
        padding: '3rem 2rem',
        textAlign: 'center',
        borderBottom: `1px solid ${colors.border}`
      }}>
        <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
          <h1 style={{
            fontSize: '3.5rem',
            fontWeight: '900',
            margin: '0 0 1rem 0',
            color: colors.textPrimary,
            letterSpacing: '-0.025em'
          }}>
            Reddit Stock Sentiment Search
          </h1>
          <p style={{
            fontSize: '1.1rem',
            color: colors.textSecondary,
            maxWidth: '700px',
            margin: '0 auto 2.5rem auto',
            lineHeight: '1.6'
          }}>
            Search any stock ticker for comprehensive sentiment analysis from 15+ finance communities
          </p>
          
          {/* Search Bar */}
          <div style={{
            position: 'relative',
            maxWidth: '600px',
            margin: '0 auto'
          }}>
            <input
              type="text"
              placeholder="Search any ticker (e.g., AAPL, TSLA, GOOGL)..."
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value)
                handleAutocomplete(e.target.value)
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  handleSearch(searchQuery)
                  setShowAutocomplete(false)
                }
              }}
              style={{
                width: '100%',
                height: '56px', // Fixed height for consistent button alignment
                padding: '0 140px 0 24px', // Right padding for button space
                fontSize: '1.1rem',
                background: colors.surface,
                border: `2px solid ${colors.border}`,
                borderRadius: '12px',
                color: colors.textPrimary,
                outline: 'none',
                fontWeight: '500',
                boxShadow: '0 4px 12px rgba(0, 0, 0, 0.1)',
                transition: 'all 0.3s ease'
              }}
              onFocus={(e) => {
                (e.target as HTMLInputElement).style.borderColor = colors.primary
                ;(e.target as HTMLInputElement).style.boxShadow = '0 6px 20px rgba(255, 255, 255, 0.1)'
                ;(e.target as HTMLInputElement).style.transform = 'translateY(-2px)'
              }}
              onBlur={(e) => {
                (e.target as HTMLInputElement).style.borderColor = colors.border
                ;(e.target as HTMLInputElement).style.boxShadow = '0 4px 12px rgba(0, 0, 0, 0.1)'
                ;(e.target as HTMLInputElement).style.transform = 'translateY(0)'
              }}
            />
            
            {/* Search Button - Properly Aligned */}
            <button
              onClick={() => {
                console.log('Search button clicked, searchQuery:', searchQuery)
                handleSearch(searchQuery)
                setShowAutocomplete(false)
              }}
              style={{
                position: 'absolute',
                right: '6px',
                top: '6px',
                bottom: '6px', // This ensures perfect vertical alignment
                width: '120px',
                background: colors.primary,
                color: colors.background,
                border: 'none',
                borderRadius: '8px',
                fontSize: '0.95rem',
                fontWeight: '600',
                cursor: 'pointer',
                transition: 'all 0.3s ease',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}
              onMouseEnter={(e) => {
                (e.target as HTMLButtonElement).style.background = colors.textSecondary
                ;(e.target as HTMLButtonElement).style.transform = 'scale(1.02)'
                ;(e.target as HTMLButtonElement).style.boxShadow = '0 4px 12px rgba(255, 255, 255, 0.2)'
              }}
              onMouseLeave={(e) => {
                (e.target as HTMLButtonElement).style.background = colors.primary
                ;(e.target as HTMLButtonElement).style.transform = 'scale(1)'
                ;(e.target as HTMLButtonElement).style.boxShadow = 'none'
              }}
            >
              Search
            </button>
            
            {/* Autocomplete Dropdown */}
            {showAutocomplete && autocompleteResults.length > 0 && (
              <div style={{
                position: 'absolute',
                top: '100%',
                left: '0',
                right: '0',
                marginTop: '0.5rem',
                background: colors.surface,
                border: `1px solid ${colors.border}`,
                borderRadius: '1rem',
                boxShadow: '0 10px 25px rgba(0, 0, 0, 0.3)',
                zIndex: 1000
              }}>
                {autocompleteResults.map((suggestion, index) => (
                  <div
                    key={index}
                    onClick={() => {
                      setSearchQuery(suggestion.ticker)
                      handleSearch(suggestion.ticker)
                      setShowAutocomplete(false)
                    }}
                    style={{
                      padding: '1rem 1.5rem',
                      cursor: 'pointer',
                      borderBottom: index < autocompleteResults.length - 1 ? `1px solid ${colors.border}` : 'none',
                      transition: 'all 0.3s ease',
                      borderRadius: index === 0 ? '1rem 1rem 0 0' : 
                                  index === autocompleteResults.length - 1 ? '0 0 1rem 1rem' : '0'
                    }}
                    onMouseEnter={(e) => {
                      (e.target as HTMLElement).style.background = colors.surfaceLight
                      ;(e.target as HTMLElement).style.transform = 'translateX(4px)'
                    }}
                    onMouseLeave={(e) => {
                      (e.target as HTMLElement).style.background = 'transparent'
                      ;(e.target as HTMLElement).style.transform = 'translateX(0)'
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div>
                        <div style={{ fontWeight: '700', fontSize: '1.1rem' }}>{suggestion.ticker}</div>
                        <div style={{ fontSize: '0.875rem', color: colors.textMuted }}>
                          {suggestion.mention_count} mentions
                        </div>
                      </div>
                      <div style={{ color: getSentimentColor(suggestion.avg_sentiment) }}>
                        {getSentimentSymbol(suggestion.avg_sentiment)}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div style={{
        background: colors.background,
        borderBottom: `2px solid ${colors.border}`
      }}>
        <div style={{
          maxWidth: '1400px',
          margin: '0 auto',
          display: 'flex',
          justifyContent: 'center'
        }}>
          {[
            { key: 'search', label: 'Search Results' },
            { key: 'trending', label: 'Trending Tickers' }
          ].map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setCurrentView(key as 'search' | 'trending')}
              style={{
                padding: '1.25rem 2rem',
                background: 'transparent',
                color: currentView === key ? colors.textPrimary : colors.textSecondary,
                border: 'none',
                borderBottom: currentView === key ? `3px solid ${colors.primary}` : `3px solid transparent`,
                cursor: 'pointer',
                fontSize: '1rem',
                fontWeight: currentView === key ? '700' : '500',
                transition: 'all 0.3s ease',
                position: 'relative'
              }}
              onMouseEnter={(e) => {
                if (currentView !== key) {
                  (e.target as HTMLButtonElement).style.color = colors.primary
                  ;(e.target as HTMLButtonElement).style.borderBottomColor = colors.textMuted
                }
              }}
              onMouseLeave={(e) => {
                if (currentView !== key) {
                  (e.target as HTMLButtonElement).style.color = colors.textSecondary
                  ;(e.target as HTMLButtonElement).style.borderBottomColor = 'transparent'
                }
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Main Content */}
      <div style={{
        maxWidth: '1400px',
        margin: '0 auto',
        padding: '2rem',
        minHeight: 'calc(100vh - 300px)', // Ensure content fills remaining space
        background: colors.background
      }}>

        {/* Search Results View */}
        {currentView === 'search' && (
          <div>
            {searchResult ? (
              searchResult.found ? (
                <div>
                  {/* Ticker Info Header */}
                  <div style={{
                    background: colors.surface,
                    padding: '2rem',
                    borderRadius: '1.5rem',
                    border: `1px solid ${colors.border}`,
                    marginBottom: '2rem',
                    transition: 'all 0.3s ease',
                    cursor: 'default'
                  }}
                  onMouseEnter={(e) => {
                    (e.target as HTMLElement).style.transform = 'translateY(-2px)'
                    ;(e.target as HTMLElement).style.boxShadow = '0 8px 25px rgba(255, 255, 255, 0.1)'
                  }}
                  onMouseLeave={(e) => {
                    (e.target as HTMLElement).style.transform = 'translateY(0)'
                    ;(e.target as HTMLElement).style.boxShadow = 'none'
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                      <h2 style={{
                        fontSize: '2.5rem',
                        fontWeight: '800',
                        margin: '0',
                        color: colors.textPrimary
                      }}>
                        ${searchResult.ticker}
                      </h2>
                      <div style={{
                        fontSize: '3rem',
                        color: getSentimentColor(searchResult.ticker_info?.avg_sentiment || 0)
                      }}>
                        {getSentimentSymbol(searchResult.ticker_info?.avg_sentiment || 0)}
                      </div>
                    </div>
                    
                    {/* Stats Grid */}
                    <div style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
                      gap: '1.5rem',
                      marginTop: '1.5rem'
                    }}>
                      <div style={{ textAlign: 'center' }}>
                        <div style={{ fontSize: '2rem', fontWeight: '800', color: colors.primary }}>
                          {searchResult.ticker_info?.total_mentions || 0}
                        </div>
                        <div style={{ fontSize: '0.875rem', color: colors.textMuted }}>Total Mentions</div>
                      </div>
                      <div style={{ textAlign: 'center' }}>
                        <div style={{ fontSize: '2rem', fontWeight: '800', color: getSentimentColor(searchResult.ticker_info?.avg_sentiment || 0) }}>
                          {(searchResult.ticker_info?.avg_sentiment || 0).toFixed(3)}
                        </div>
                        <div style={{ fontSize: '0.875rem', color: colors.textMuted }}>Avg Sentiment</div>
                      </div>
                      <div style={{ textAlign: 'center' }}>
                        <div style={{ fontSize: '2rem', fontWeight: '800', color: colors.accent }}>
                          {searchResult.timeline.length}
                        </div>
                        <div style={{ fontSize: '0.875rem', color: colors.textMuted }}>Active Days</div>
                      </div>
                    </div>
                  </div>
                  
                  {/* Timeline */}
                  {searchResult.timeline.length > 0 && (
                    <div style={{
                      background: colors.surface,
                      padding: '2rem',
                      borderRadius: '1.5rem',
                      border: `1px solid ${colors.border}`,
                      marginBottom: '2rem'
                    }}>
                      <h3 style={{ margin: '0 0 1.5rem 0', color: colors.textPrimary }}>Sentiment Timeline</h3>
                      <div style={{ display: 'grid', gap: '1rem' }}>
                        {searchResult.timeline.slice(0, 10).map((day, index) => (
                          <div key={index} style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            padding: '1rem',
                            background: colors.surfaceLight,
                            borderRadius: '0.5rem'
                          }}>
                            <div style={{ fontWeight: '600' }}>{new Date(day.date).toLocaleDateString()}</div>
                            <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
                              <span style={{ color: colors.textMuted }}>{day.mentions} mentions</span>
                              <span style={{
                                color: getSentimentColor(day.avg_sentiment),
                                fontWeight: '700'
                              }}>
                                {day.avg_sentiment.toFixed(3)} {getSentimentSymbol(day.avg_sentiment)}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  
                  {/* Recent Posts */}
                  {searchResult.recent_posts.length > 0 && (
                    <div style={{
                      background: colors.surface,
                      padding: '2rem',
                      borderRadius: '1.5rem',
                      border: `1px solid ${colors.border}`
                    }}>
                      <h3 style={{ margin: '0 0 1.5rem 0', color: colors.textPrimary }}>Recent Reddit Posts</h3>
                      <div style={{ display: 'grid', gap: '1rem' }}>
                        {searchResult.recent_posts.slice(0, 10).map((post, index) => (
                          <div key={index} style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            padding: '1rem',
                            background: colors.surfaceLight,
                            borderRadius: '0.5rem'
                          }}>
                            <div>
                              <div style={{ fontSize: '0.875rem', color: colors.textMuted }}>
                                {new Date(post.scored_ts).toLocaleDateString()}
                              </div>
                            </div>
                            <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
                              <span style={{
                                color: getSentimentColor(post.score),
                                fontWeight: '700'
                              }}>
                                {post.score.toFixed(3)} {getSentimentSymbol(post.score)}
                              </span>
                              <a
                                href={post.reddit_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                style={{
                                  padding: '0.75rem 1.25rem',
                                  background: colors.primary,
                                  color: colors.background,
                                  textDecoration: 'none',
                                  borderRadius: '8px',
                                  fontSize: '0.875rem',
                                  fontWeight: '600',
                                  transition: 'all 0.3s ease',
                                  display: 'inline-block'
                                }}
                                onMouseEnter={(e) => {
                                  (e.target as HTMLElement).style.background = colors.textSecondary
                                  ;(e.target as HTMLElement).style.transform = 'translateY(-1px) scale(1.05)'
                                  ;(e.target as HTMLElement).style.boxShadow = '0 4px 12px rgba(255, 255, 255, 0.2)'
                                }}
                                onMouseLeave={(e) => {
                                  (e.target as HTMLElement).style.background = colors.primary
                                  ;(e.target as HTMLElement).style.transform = 'translateY(0) scale(1)'
                                  ;(e.target as HTMLElement).style.boxShadow = 'none'
                                }}
                              >
                                View Post
                              </a>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div style={{
                  textAlign: 'center',
                  padding: '4rem 2rem',
                  color: colors.textMuted
                }}>
                  <div style={{ fontSize: '4rem', marginBottom: '1rem', color: colors.textSecondary }}>●</div>
                  <h3 style={{ fontSize: '1.5rem', margin: '0 0 0.5rem 0', color: colors.textSecondary }}>
                    No data found for "{searchResult.ticker}"
                  </h3>
                  <p>This ticker hasn't been mentioned in our monitored communities yet.</p>
                </div>
              )
            ) : (
              <div style={{
                textAlign: 'center',
                padding: '4rem 2rem',
                color: colors.textMuted
              }}>
                <div style={{ fontSize: '4rem', marginBottom: '1rem', color: colors.textSecondary }}>■</div>
                <h3 style={{ fontSize: '1.5rem', margin: '0 0 0.5rem 0', color: colors.textSecondary }}>
                  Search for any stock ticker
                </h3>
                <p>Enter a ticker symbol above to analyze sentiment from Reddit's finance communities</p>
              </div>
            )}
          </div>
        )}

        {/* Trending View */}
        {currentView === 'trending' && (
          <div>
            {/* Trending Tabs */}
            <div style={{
              display: 'flex',
              justifyContent: 'center',
              gap: '1rem',
              marginBottom: '2rem'
            }}>
              {[
                { period: '24h', label: 'Today', data: trendingData.daily },
                { period: '7d', label: 'This Week', data: trendingData.weekly },
                { period: '30d', label: 'This Month', data: trendingData.monthly }
              ].map(({ period, label, data }) => (
                <div key={period} style={{
                  background: colors.surface,
                  padding: '2rem',
                  borderRadius: '1.5rem',
                  border: `1px solid ${colors.border}`,
                  minWidth: '300px'
                }}>
                  <h3 style={{
                    margin: '0 0 1.5rem 0',
                    color: colors.textPrimary,
                    textAlign: 'center',
                    fontSize: '1.25rem'
                  }}>
                    ▲ {label}
                  </h3>
                  
                  {data.length > 0 ? (
                    <div style={{ display: 'grid', gap: '1rem' }}>
                      {data.slice(0, 10).map((ticker, index) => (
                        <div key={ticker.ticker} style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          padding: '1rem 1.5rem',
                          background: colors.surfaceLight,
                          borderRadius: '12px',
                          cursor: 'pointer',
                          transition: 'all 0.3s ease',
                          border: `1px solid transparent`
                        }}
                        onClick={() => {
                          setSearchQuery(ticker.ticker)
                          handleSearch(ticker.ticker)
                        }}
                        onMouseEnter={(e) => {
                          (e.target as HTMLElement).style.background = colors.surface
                          ;(e.target as HTMLElement).style.transform = 'translateY(-2px) scale(1.02)'
                          ;(e.target as HTMLElement).style.borderColor = colors.primary
                          ;(e.target as HTMLElement).style.boxShadow = '0 4px 15px rgba(255, 255, 255, 0.1)'
                        }}
                        onMouseLeave={(e) => {
                          (e.target as HTMLElement).style.background = colors.surfaceLight
                          ;(e.target as HTMLElement).style.transform = 'translateY(0) scale(1)'
                          ;(e.target as HTMLElement).style.borderColor = 'transparent'
                          ;(e.target as HTMLElement).style.boxShadow = 'none'
                        }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <span style={{
                              background: colors.primary,
                              color: 'white',
                              width: '1.5rem',
                              height: '1.5rem',
                              borderRadius: '50%',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              fontSize: '0.75rem',
                              fontWeight: '700'
                            }}>
                              {index + 1}
                            </span>
                            <span style={{ fontWeight: '700', fontSize: '1.1rem' }}>
                              {ticker.ticker}
                            </span>
                            <span style={{ color: getSentimentColor(ticker.avg_sentiment) }}>
                              {getSentimentSymbol(ticker.avg_sentiment)}
                            </span>
                          </div>
                          
                          <div style={{ textAlign: 'right' }}>
                            <div style={{ fontSize: '0.875rem', fontWeight: '600', color: colors.textPrimary }}>
                              {ticker.mention_count} mentions
                            </div>
                            <div style={{
                              fontSize: '0.75rem',
                              color: getSentimentColor(ticker.avg_sentiment),
                              fontWeight: '600'
                            }}>
                              {ticker.avg_sentiment.toFixed(3)}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div style={{
                      textAlign: 'center',
                      padding: '2rem',
                      color: colors.textMuted
                    }}>
                      <div style={{ fontSize: '2rem', marginBottom: '0.5rem', color: colors.textMuted }}>●</div>
                      <p style={{ margin: '0', fontSize: '0.875rem' }}>No trending data yet</p>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div style={{
        background: colors.surface,
        padding: '2rem',
        textAlign: 'center',
        borderTop: `1px solid ${colors.border}`
      }}>
        <div style={{ color: colors.textMuted, fontSize: '0.875rem' }}>
          Powered by FinBERT AI • Updates every 5 minutes • Data from 11+ finance subreddits
        </div>
      </div>
    </div>
  )
}

export default App