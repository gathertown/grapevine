import { memo, useState, useEffect, useCallback } from 'react';
import type { FC } from 'react';
import { Flex, Text, Button, Input } from '@gathertown/gather-design-system';
import { ThreadCard } from './ThreadCard';
import { SplitStatistics } from './SplitStatistics';
import {
  statsApi,
  type ThreadStat,
  type StatsSummary,
  type ThreadStatsFilters,
} from '../api/stats';

const StatsPage: FC = memo(() => {
  const [threads, setThreads] = useState<ThreadStat[]>([]);
  const [summary, setSummary] = useState<StatsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);

  // Filter state
  const [dateFilter, setDateFilter] = useState<'all' | 'today' | 'week' | 'month'>('all');
  const [customDateFrom, setCustomDateFrom] = useState('');
  const [customDateTo, setCustomDateTo] = useState('');

  // Calculate date range based on filter
  const getDateRange = useCallback((): { date_from?: string; date_to?: string } => {
    const now = new Date();

    switch (dateFilter) {
      case 'today': {
        const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        return {
          date_from: today.toISOString(),
        };
      }
      case 'week': {
        const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
        return {
          date_from: weekAgo.toISOString(),
        };
      }
      case 'month': {
        const monthAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
        return {
          date_from: monthAgo.toISOString(),
        };
      }
      default:
        return {};
    }
  }, [dateFilter]);

  // Load initial data
  const loadData = useCallback(
    async (reset = true) => {
      try {
        if (reset) {
          setLoading(true);
          setError(null);
        } else {
          setLoadingMore(true);
        }

        const dateRange = getDateRange();
        const filters: ThreadStatsFilters = {
          page: reset ? 1 : currentPage,
          limit: 20,
          ...dateRange,
        };

        // Use custom dates if provided
        if (customDateFrom) filters.date_from = customDateFrom;
        if (customDateTo) filters.date_to = customDateTo;

        const [threadsResponse, summaryResponse] = await Promise.all([
          statsApi.getThreadStats(filters),
          reset ? statsApi.getSummaryStats(dateRange) : Promise.resolve(null),
        ]);

        if (reset) {
          setThreads(threadsResponse.threads);
          setCurrentPage(2);
          if (summaryResponse) {
            setSummary(summaryResponse);
          }
        } else {
          setThreads((prev) => [...prev, ...threadsResponse.threads]);
          setCurrentPage((prev) => prev + 1);
        }

        setHasMore(threadsResponse.hasMore);
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'Failed to load data';
        setError(errorMessage);
        console.error('Error loading stats data:', err);
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [getDateRange, customDateFrom, customDateTo, currentPage]
  );

  // Initial load
  useEffect(() => {
    loadData(true);
  }, [dateFilter, customDateFrom, customDateTo]); // eslint-disable-line react-hooks/exhaustive-deps

  // Load more handler
  const handleLoadMore = useCallback(() => {
    if (!loadingMore && hasMore) {
      loadData(false);
    }
  }, [loadData, loadingMore, hasMore]);

  // Handle date filter change
  const handleDateFilterChange = (newFilter: typeof dateFilter) => {
    setDateFilter(newFilter);
    setCustomDateFrom('');
    setCustomDateTo('');
  };

  if (loading && threads.length === 0) {
    return (
      <Flex
        direction="column"
        align="center"
        justify="center"
        p={32}
        backgroundColor="primary"
        borderRadius={8}
        maxWidth={1200}
        minHeight="100vh"
      >
        {/* <div className={styles.spinner}></div> */}
        <Text fontSize="lg">Loading bot interaction statistics...</Text>
      </Flex>
    );
  }

  if (error) {
    return (
      <Flex
        direction="column"
        align="center"
        justify="center"
        p={32}
        backgroundColor="primary"
        borderRadius={8}
        maxWidth={1200}
        mx="auto"
        minHeight="100vh"
      >
        <Text fontSize="xl">Error Loading Stats</Text>
        <Text fontSize="md">{error}</Text>
        <Button onClick={() => loadData(true)} kind="primary">
          Try Again
        </Button>
      </Flex>
    );
  }

  return (
    <Flex direction="column" maxWidth={1200} gap={24}>
      {summary && <SplitStatistics summary={summary} />}

      <Flex direction="column" p={24} backgroundColor="primary" borderRadius={8} gap={20}>
        <Flex gap={8} flexWrap="wrap">
          <Button
            kind={dateFilter === 'all' ? 'primary' : 'secondary'}
            size="md"
            onClick={() => handleDateFilterChange('all')}
          >
            All Time
          </Button>
          <Button
            kind={dateFilter === 'today' ? 'primary' : 'secondary'}
            size="md"
            onClick={() => handleDateFilterChange('today')}
          >
            Today
          </Button>
          <Button
            kind={dateFilter === 'week' ? 'primary' : 'secondary'}
            size="md"
            onClick={() => handleDateFilterChange('week')}
          >
            Last 7 Days
          </Button>
          <Button
            kind={dateFilter === 'month' ? 'primary' : 'secondary'}
            size="md"
            onClick={() => handleDateFilterChange('month')}
          >
            Last 30 Days
          </Button>
        </Flex>

        <Flex gap={16} flexWrap="wrap" align="flex-end">
          <Flex direction="column" gap={4}>
            <Text fontSize="sm">From:</Text>
            <Input
              type="datetime-local"
              value={customDateFrom}
              onChange={(e) => setCustomDateFrom(e.target.value)}
            />
          </Flex>
          <Flex direction="column" gap={4}>
            <Text fontSize="sm">To:</Text>
            <Input
              type="datetime-local"
              value={customDateTo}
              onChange={(e) => setCustomDateTo(e.target.value)}
            />
          </Flex>
        </Flex>
      </Flex>

      <Flex
        direction="column"
        backgroundColor="primary"
        borderRadius={8}
        overflow="hidden"
        style={{ height: 'calc(100vh - 300px)' }}
      >
        {threads.length === 0 ? (
          <Flex align="center" justify="center" p={32}>
            <Text fontSize="lg">No Q&A interactions found for the selected time period.</Text>
          </Flex>
        ) : (
          <>
            <Flex
              p={16}
              px={20}
              backgroundColor="secondary"
              direction="row"
              justify="space-between"
              align="center"
              minHeight={68}
            >
              <Text fontSize="lg" fontWeight="inherit">
                Showing {threads.length} interactions
                {summary && ` of ${summary.totalMessages} total`}
              </Text>
              {hasMore && (
                <Button
                  onClick={handleLoadMore}
                  disabled={loadingMore}
                  kind="secondary"
                  size="lg"
                  loading={loadingMore}
                  loadingText="Loading more..."
                >
                  Load More
                </Button>
              )}
            </Flex>

            <Flex direction="column" p={20} gap={12} style={{ flex: 1, overflowY: 'auto' }}>
              {threads.map((thread) => (
                <ThreadCard key={thread.message_id} thread={thread} />
              ))}
            </Flex>
          </>
        )}
      </Flex>
    </Flex>
  );
});

StatsPage.displayName = 'StatsPage';

export { StatsPage };
