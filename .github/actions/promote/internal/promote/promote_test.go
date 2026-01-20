package promote

import (
	"strings"
	"testing"

	gogithub "github.com/google/go-github/v76/github"
	"github.com/jaredallard/slogext"
	"github.com/jaredallard/vcs"
	"github.com/jaredallard/vcs/token"
	"gotest.tools/v3/assert"
)

// newTestClient returns a new [Client] for testing
func newTestClient(t *testing.T) *Client {
	tok, _ := token.Fetch(t.Context(), vcs.ProviderGithub, false)
	return &Client{
		log: slogext.NewTestLogger(t),
		gh:  gogithub.NewClient(nil).WithAuthToken(tok.Value),
	}
}

func TestCanCalculateAPromotion(t *testing.T) {
	ctx := t.Context()
	c := newTestClient(t)
	promotion, err := c.calculatePromotion(ctx,
		"gathertown", "corporate-context",
		// https://github.com/gathertown/corporate-context/commit/668977dc7ad3a410c7d12fe7234c5436886c16bc
		"668977dc7ad3a410c7d12fe7234c5436886c16bc",
		// https://github.com/gathertown/corporate-context/commit/ab711e28ac38c9aef50cb9718927cb05e2bca9e9
		"ab711e28ac38c9aef50cb9718927cb05e2bca9e9",
		EnvironmentProduction,
		false,
	)
	assert.NilError(t, err, "expected calculatePromotion() to not fail")

	assert.Equal(t, len(promotion.Commits), 1, "expected one commit to be promoted")
	assert.Equal(t, len(promotion.PRs), 1, "expected one PR to be found")
	assert.Equal(t, promotion.PRs[1588].Approved, false, "expected PR to be not approved")
}

func TestShowsWarningWhenUnreviewedPRsExist(t *testing.T) {
	ctx := t.Context()
	c := newTestClient(t)
	promotion, err := c.calculatePromotion(ctx,
		"gathertown", "corporate-context",
		// https://github.com/gathertown/corporate-context/commit/668977dc7ad3a410c7d12fe7234c5436886c16bc
		"668977dc7ad3a410c7d12fe7234c5436886c16bc",
		// https://github.com/gathertown/corporate-context/commit/ab711e28ac38c9aef50cb9718927cb05e2bca9e9
		"ab711e28ac38c9aef50cb9718927cb05e2bca9e9",
		EnvironmentProduction,
		false,
	)
	assert.NilError(t, err, "expected calculatePromotion() to not fail")

	assert.Assert(t, strings.Contains(promotion.PRBody, "[!WARNING]"), "expected PR body to contain an error")
}
