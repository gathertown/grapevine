package promote

import (
	"context"
	"fmt"

	gogithub "github.com/google/go-github/v76/github"
)

// paginateGitHubAPI is a generic function that handles GitHub API
// pagination. It takes a fetcher function that makes the API call for a
// given page and returns items, the response, and any error. It returns
// all collected items.
func paginateGitHubAPI[T any](ctx context.Context, fetcher func(ctx context.Context, page int) ([]T, *gogithub.Response, error)) ([]T, error) {
	var items []T
	var page int

	for {
		newItems, resp, err := fetcher(ctx, page)
		if err != nil {
			return nil, fmt.Errorf("failed to fetch page %d: %w", page, err)
		}

		items = append(items, newItems...)

		if resp.NextPage == 0 {
			break
		}
		page = resp.NextPage
	}

	return items, nil
}
