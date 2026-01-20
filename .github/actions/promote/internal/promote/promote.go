// Package promote implements promotion logic.
package promote

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"os"
	"regexp"
	"strconv"
	"strings"
	"text/template"
	"time"

	_ "embed"

	"github.com/Masterminds/sprig/v3"
	"github.com/cenkalti/backoff/v4"
	gogithub "github.com/google/go-github/v76/github"
	"github.com/jaredallard/cmdexec"
	"github.com/jaredallard/slogext"
	"github.com/jaredallard/vcs"
	"github.com/jaredallard/vcs/token"
)

//go:embed embed/pr-body.md.tpl
var prBodyTemplateText string
var prBodyTemplate = template.Must(
	template.New("pr-body.md.tpl").
		Funcs(sprig.TxtFuncMap()).
		Parse(prBodyTemplateText),
)

var parsePRRegex = regexp.MustCompile(`\(#(\d+)\)$`)

// ToPtr returns a pointer to the given value.
func ToPtr[T any](v T) *T {
	return &v
}

var (
	// ErrNoChanges is returned when the desired commit is already the
	// base, or there is otherwise no changes between two given
	// commits/refs.
	ErrNoChanges = errors.New("no changes")
)

type Client struct {
	log slogext.Logger
	gh  *gogithub.Client
}

// Promotion contains information about a given promotion.
type Promotion struct {
	// Environment is the environment being promoted to.
	Environment Environment

	// Commit is the commit being promoted to the given environment.
	Commit string

	// Branch is the name of the branch used for this promotion. This is
	// NOT the base (environment) branch name.
	Branch string

	// BaseCommit is the commit that [Promotion.Environment] is currently
	// at.
	BaseCommit string

	// Commits are the commits apart of this promotion.
	Commits []PromotionCommit

	// PRs contains the PRs apart of this promotion.
	PRs map[int]*PromotionPR

	// Hotfix denotes if this is a hotfix or not.
	Hotfix bool

	// PRBody contains the body of the PR to be created for this
	// promotion. This is not available at execution time for the pr body
	// template.
	PRBody string
}

type PromotionCommit struct {
	// PR is the PR associated with this commit, if any.
	PR int

	// Commit is the commit information returned by Github for this
	// commit.
	Commit *gogithub.RepositoryCommit
}

type PromotionPR struct {
	// Approved denotes if this PR was approved.
	Approved bool
}

// NewClient returns a fully initialized Github client using default
// Github credentials on the system via [token.Fetch].
func NewClient(ctx context.Context) *Client {
	t, err := token.Fetch(ctx, vcs.ProviderGithub, false)
	if err != nil {
		panic(fmt.Errorf("failed to get github token: %v", err))
	}
	return &Client{
		log: slogext.New(),
		gh:  gogithub.NewClient(nil).WithAuthToken(t.Value),
	}
}

// getBaseCommit returns the base commit of a given branch filtering out
// specific users (currently, github-actions[bot] commits)
func (c *Client) getBaseCommit(ctx context.Context, org, repo, commit, envBranch string) (string, error) {
	commits, _, err := c.gh.Repositories.ListCommits(ctx, org, repo, &gogithub.CommitsListOptions{
		SHA: envBranch,
		ListOptions: gogithub.ListOptions{
			PerPage: 5,
		},
	})
	if err != nil {
		return "", fmt.Errorf("failed to list commits for branch %s: %w", envBranch, err)
	}

	if len(commits) == 0 {
		return "", fmt.Errorf("no commits were returned for SHA/ref %s", envBranch)
	}

	var baseCommit string
	for _, commit := range commits {
		if commit.GetAuthor().GetLogin() == "github-actions[bot]" {
			c.log.Info("ignoring commit", "author", commit.GetAuthor().GetLogin(), "commit", commit.GetSHA())
			continue
		}

		baseCommit = commit.GetSHA()
		break
	}
	if baseCommit == "" {
		return "", fmt.Errorf("unable to find non filtered commit")
	}

	return baseCommit, nil
}

// calculatePromotion calculates the commits, PRs, and other information
// involved in a given promotion from the Github API.
func (c *Client) calculatePromotion(ctx context.Context, org, repo, commit, baseCommit string, env Environment, hotfix bool) (*Promotion, error) {
	prefix := "promotions"
	if hotfix {
		prefix = "hotfix"
	}

	promotion := &Promotion{
		Environment: env,
		Commit:      commit,
		Branch:      fmt.Sprintf("generated/%s/%s-%s", prefix, commit, env),
		BaseCommit:  baseCommit,
		Hotfix:      hotfix,
		PRs:         make(map[int]*PromotionPR),
	}

	// Get commits between base & head (commits that will be promoted)
	commits, err := paginateGitHubAPI(ctx, func(ctx context.Context, page int) ([]*gogithub.RepositoryCommit, *gogithub.Response, error) {
		newCommits, resp, err := c.gh.Repositories.CompareCommits(ctx, org, repo, baseCommit, commit, &gogithub.ListOptions{
			PerPage: 100,
			Page:    page,
		})
		if err != nil {
			return nil, resp, err
		}
		return newCommits.Commits, resp, nil
	})
	if err != nil {
		return nil, fmt.Errorf("failed to fetch commits between base and head: %w", err)
	}

	promotion.Commits = make([]PromotionCommit, 0, len(commits))

	c.log.Infof("found %d commit(s) in promotion", len(commits))

	// Get PRs from commits
	for i := range commits {
		commit := commits[i]

		msg := strings.Split(commit.Commit.GetMessage(), "\n")[0]
		matches := parsePRRegex.FindAllString(msg, -1)

		var pr int
		if matches != nil {
			match := strings.TrimLeft(strings.TrimRight(matches[len(matches)-1], ")"), "(#")

			var err error
			pr, err = strconv.Atoi(match)
			if err != nil {
				return nil, fmt.Errorf("failed to parse %s as PR number: %w", match, err)
			}

			c.log.Info("parsed commit", "commit.msg", msg, "pr", pr)
			if _, ok := promotion.PRs[pr]; !ok {
				promotion.PRs[pr] = &PromotionPR{}
			}
		} else {
			c.log.Warn("commit had no detectable PR associated with it", "commit.msg", msg)
		}

		promotion.Commits = append(promotion.Commits, PromotionCommit{
			PR:     pr,
			Commit: commit,
		})
	}

	// Check if PRs were approved
	for num := range promotion.PRs {
		reviews, err := paginateGitHubAPI(ctx, func(ctx context.Context, page int) ([]*gogithub.PullRequestReview, *gogithub.Response, error) {
			return c.gh.PullRequests.ListReviews(ctx, org, repo, num, &gogithub.ListOptions{
				PerPage: 100,
				Page:    page,
			})
		})
		if err != nil {
			return nil, fmt.Errorf("failed to fetch reviews for PR %d: %w", num, err)
		}
		if len(reviews) == 0 {
			continue
		}

		for _, rev := range reviews {
			c.log.Info("processing review", "pr", num, "state", rev.GetState())
			if rev.GetState() != "APPROVED" {
				continue
			}

			promotion.PRs[num].Approved = true
		}
	}

	var body bytes.Buffer
	if err := prBodyTemplate.Execute(&body, promotion); err != nil {
		return nil, fmt.Errorf("failed to generate PR body: %w", err)
	}
	promotion.PRBody = body.String()

	return promotion, nil
}

// createBranch creates the given branch at the provided commit. If
// it already exists, it is recreated.
func (c *Client) createBranch(ctx context.Context, org, repo, commit, branchName string) error {
	// Create a branch for the promotion to be merged into
	refName := fmt.Sprintf("refs/heads/%s", branchName)
	_, resp, err := c.gh.Git.GetRef(ctx, org, repo, refName)
	if err == nil {
		c.log.Info("branch already exists, deleting it", "branch", branchName)
		if _, err := c.gh.Git.DeleteRef(ctx, org, repo, refName); err != nil {
			return fmt.Errorf("failed to delete existing branch %s: %w", branchName, err)
		}
	} else if resp != nil && resp.StatusCode != 404 {
		return fmt.Errorf("failed to check if branch %s exists: %w", branchName, err)
	}

	// Wait until the branch doesn't exist
	if err := backoff.Retry(func() error {
		_, resp, _ := c.gh.Git.GetRef(ctx, org, repo, refName)
		if resp != nil && resp.StatusCode == 404 {
			return nil
		}

		return fmt.Errorf("branch exists")
	}, backoff.NewExponentialBackOff(backoff.WithMaxElapsedTime(time.Minute*5))); err != nil {
		return fmt.Errorf("failed to ensure branch no longer exists: %w", err)
	}

	_, _, err = c.gh.Git.CreateRef(ctx, org, repo, gogithub.CreateRef{
		Ref: refName,
		SHA: commit,
	})
	if err != nil {
		return fmt.Errorf("failed to create branch %s: %w", branchName, err)
	}

	return nil
}

// CreatePR creates a PR to promote the given environment. Returns the
// URL of the created PR.
func (c *Client) CreatePR(ctx context.Context, org, repo, commit string, env Environment) (string, error) {
	c.log.Info("starting promotion PR creation", "repo", org+"/"+repo, "env", env, "commit", commit)
	envBranch := env.GetBranch()
	baseCommit, err := c.getBaseCommit(ctx, org, repo, commit, envBranch)
	if err != nil {
		return "", fmt.Errorf("failed to get base commit of branch %s: %w", envBranch, err)
	}

	c.log.Info("determined base commit", "commit", baseCommit)
	if baseCommit == commit {
		return "", ErrNoChanges
	}

	promotion, err := c.calculatePromotion(ctx, org, repo, commit, baseCommit, env, false)
	if err != nil {
		return "", fmt.Errorf("failed to calculate promotion: %w", err)
	}

	if err := c.createBranch(ctx, org, repo, commit, promotion.Branch); err != nil {
		return "", fmt.Errorf("failed to create promotion branch: %w", err)
	}

	c.log.Info("created promotion branch", "branch", promotion.Branch)

	pr, _, err := c.gh.PullRequests.Create(ctx, org, repo, &gogithub.NewPullRequest{
		Title: ToPtr(fmt.Sprintf("deploy: promote %s to %s", promotion.Commit, promotion.Environment)),
		Body:  &promotion.PRBody,
		Base:  ToPtr(promotion.Environment.GetBranch()),
		Head:  &promotion.Branch,
	})
	if err != nil {
		return "", fmt.Errorf("failed to create PR: %w", err)
	}

	if err := c.UpdateStatusCheck(ctx, org, repo, pr.GetNumber(), promotion); err != nil {
		return "", fmt.Errorf("failed to update PR status check %d: %w", pr.GetNumber(), err)
	}

	return pr.GetHTMLURL(), nil
}

// UpdateStatusCheck updates the status check on the given PR to reflect
// if all PRs have been approved or not. If [promotion] is not provided
// it is automatically generated.
func (c *Client) UpdateStatusCheck(ctx context.Context, org, repo string, prNum int, promotion *Promotion) error {
	startedAt := time.Now().UTC()

	if promotion == nil {
		var err error
		pr, _, err := c.gh.PullRequests.Get(ctx, org, repo, prNum)
		if err != nil {
			return fmt.Errorf("failed to lookup PR %d: %w", prNum, err)
		}

		// TODO(jaredallard): Support other environments (e.g., parse from
		// branch name)
		promotion, err = c.calculatePromotion(ctx, org, repo,
			pr.GetHead().GetSHA(), pr.GetBase().GetSHA(), EnvironmentProduction, false,
		)
		if err != nil {
			return fmt.Errorf("failed to calculate status of promotion")
		}
	}

	// Determine if all PRs are approved
	allApproved := true
	for _, pr := range promotion.PRs {
		if !pr.Approved {
			allApproved = false
			break
		}
	}

	checkName := "promote/pr-approval"
	state := "success"
	description := "All PRs have been approved"
	if !allApproved {
		state = "failure"
		description = "Not all PRs have been approved"
	}

	checkRun := gogithub.CreateCheckRunOptions{
		Name:        checkName,
		HeadSHA:     promotion.Commit,
		Status:      ToPtr("completed"),
		StartedAt:   &gogithub.Timestamp{Time: startedAt},
		CompletedAt: &gogithub.Timestamp{Time: time.Now().UTC()},
		Conclusion:  &state,
		Output:      &gogithub.CheckRunOutput{Title: &description, Summary: ToPtr("See title.")},
	}
	if _, _, err := c.gh.Checks.CreateCheckRun(ctx, org, repo, checkRun); err != nil {
		return fmt.Errorf("failed to create status check: %w", err)
	}

	return nil
}

// UpdatePRStatus checks the status of all of the commits in a given
// promotion PR, updates the open PR's body and updates the status
// check on the PR to reflect if they've all been approved or not.
func (c *Client) UpdatePRStatus(ctx context.Context, org, repo string, prNum int) error {
	pr, _, err := c.gh.PullRequests.Get(ctx, org, repo, prNum)
	if err != nil {
		return fmt.Errorf("failed to lookup PR %d: %w", prNum, err)
	}

	var hotfix bool
	if strings.HasPrefix(pr.GetBase().GetRef(), "deploy-queue-hotfix/") {
		hotfix = true
	}

	// TODO(jaredallard): Support other environments (e.g., parse from
	// branch name)
	promotion, err := c.calculatePromotion(ctx, org, repo,
		pr.GetHead().GetSHA(), pr.GetBase().GetSHA(), EnvironmentProduction, hotfix,
	)
	if err != nil {
		return fmt.Errorf("failed to calculate status of promotion")
	}

	if _, _, err := c.gh.PullRequests.Edit(ctx, org, repo, prNum, &gogithub.PullRequest{
		Body: &promotion.PRBody,
	}); err != nil {
		return fmt.Errorf("failed to update PR body")
	}

	if err := c.UpdateStatusCheck(ctx, org, repo, pr.GetNumber(), promotion); err != nil {
		return fmt.Errorf("failed to update PR status check %d: %w", pr.GetNumber(), err)
	}

	return nil
}

// CreateHotfixPR creates a hotfix PR into the production environment
// for the given commit SHA.
func (c *Client) CreateHotfixPR(ctx context.Context, org, repo, hotfixCommit string) error {
	env := EnvironmentProduction
	deployQueueBranchName := env.GetBranch()
	hotfixQueueBranchName := env.GetHotfixBranch()
	deployBranchName := env.GetDeployBranch()
	if hotfixQueueBranchName == "" {
		return fmt.Errorf("environment does not support hotfixes")
	}

	deployQueueBranch, _, err := c.gh.Repositories.GetBranch(ctx, org, repo, deployQueueBranchName, 2)
	if err != nil {
		return fmt.Errorf("failed to get deploy queue branch %q: %w", deployQueueBranchName, err)
	}
	deployQueueHEAD := deployQueueBranch.GetCommit().GetSHA()

	// TODO(jaredallard): We need the branch to exist before we can run
	// the promotion calculation logic. Because of this, we have to
	// duplicate the branch name logic here. We should remove this in the future.
	promotionBranchName := fmt.Sprintf("generated/hotfix/%s-%s", hotfixCommit, env)

	if err := c.createBranch(ctx, org, repo, deployQueueHEAD, promotionBranchName); err != nil {
		return fmt.Errorf("failed to create hotfix branch: %w", err)
	}

	c.log.Info("created hotfix branch", "branch", promotionBranchName)

	tmpDir, err := os.MkdirTemp("", "hotfix-pr-*")
	if err != nil {
		return fmt.Errorf("failed to create temp dir: %w", err)
	}
	defer os.Remove(tmpDir)

	// Get the commits between deploy branch (e.g., prod) and the queue
	// branch to know if there's any other hotfixes we need to re-apply.
	commits, err := paginateGitHubAPI(ctx, func(ctx context.Context, page int) ([]*gogithub.RepositoryCommit, *gogithub.Response, error) {
		cc, resp, err := c.gh.Repositories.CompareCommits(ctx, org, repo, deployQueueBranchName, deployBranchName, &gogithub.ListOptions{
			Page:    page,
			PerPage: 100,
		})
		if err != nil {
			return nil, resp, err
		}

		return cc.Commits, resp, err
	})
	if err != nil {
		return fmt.Errorf("failed to get commits between %s and %s: %w", deployQueueBranchName, deployBranchName, err)
	}

	if len(commits) != 0 {
		// Note: at least 1 is expected right now because we generate an
		// image digests commit and push that as part of CI.
		c.log.Info("deploy branch is ahead of deploy queue branch (one is expected)", "commits.len", len(commits))
	}

	otherHotfixCommits := make([]string, 0)
	for _, commit := range commits {
		// Skip commits from GHA, these are automatically generated commits,
		// not hotfixes.
		if commit.GetAuthor().GetLogin() == "github-actions[bot]" {
			continue
		}

		// Skip merge commits
		if len(commit.Parents) > 1 || len(commit.GetCommit().Parents) > 1 {
			continue
		}

		if commit.GetSHA() == "" {
			// Skip commits without a SHA (how would this happen?)
			continue
		}

		c.log.Info("found another hotfix", "commit.sha", commit.GetSHA(), "commit.msg", commit.GetCommit().GetMessage())
		otherHotfixCommits = append(otherHotfixCommits, commit.GetSHA())
	}

	if len(otherHotfixCommits) != 0 {
		c.log.Warn("found other hotfixes, they will be applied with this PR")
	}

	commands := [][]string{
		{"git", "clone", fmt.Sprintf("https://github.com/%s/%s", org, repo), tmpDir},
		{"git", "fetch", "origin", promotionBranchName},
		{"git", "checkout", promotionBranchName},
	}

	for _, commit := range append(
		// Apply previous hotfixes first
		append([]string{}, otherHotfixCommits...),
		// Then apply our new hotfix
		hotfixCommit,
	) {
		commands = append(commands, []string{"git", "cherry-pick", commit})
	}

	commands = append(commands, []string{"git", "push", "origin", promotionBranchName})

	for _, command := range commands {
		c.log.Info("running command", "command", command[0], "args", command[1:])
		cmd := cmdexec.CommandContext(ctx, command[0], command[1:]...)
		cmd.SetDir(tmpDir)
		cmd.UseOSStreams(false)
		if err := cmd.Run(); err != nil {
			return fmt.Errorf("failed to run '%s': %w", command, err)
		}
	}

	promotionBranchHEAD, err := backoff.RetryWithData(func() (string, error) {
		promotionBranch, _, err := c.gh.Repositories.GetBranch(ctx, org, repo, promotionBranchName, 2)
		if err != nil {
			return "", err
		}

		return promotionBranch.GetCommit().GetSHA(), nil
	}, backoff.NewExponentialBackOff(backoff.WithMaxElapsedTime(time.Minute*5)))
	if err != nil {
		return fmt.Errorf("failed to get promotion branch HEAD: %w", err)
	}

	// deploy-queue-hotfix/<env> has to match deploy-queue/<env>, so we
	// recreate it here. Otherwise, we could accidentally revert already
	// promoted commits.
	if err := c.createBranch(ctx, org, repo, deployQueueHEAD, hotfixQueueBranchName); err != nil {
		return fmt.Errorf("failed to reset hotfix deploy queue: %w", err)
	}

	promotion, err := c.calculatePromotion(ctx, org, repo, promotionBranchHEAD, deployQueueHEAD, env, true)
	if err != nil {
		return fmt.Errorf("failed to calculate promotion: %w", err)
	}

	pr, _, err := c.gh.PullRequests.Create(ctx, org, repo, &gogithub.NewPullRequest{
		Title: ToPtr(fmt.Sprintf("deploy(hotfix): HOTFIX %s to %s", hotfixCommit, env)),
		Head:  &promotionBranchName,
		Base:  &hotfixQueueBranchName,
		Body:  &promotion.PRBody,
	})
	if err != nil {
		return fmt.Errorf("failed to create hotfix PR: %w", err)
	}

	c.log.Info("created PR", "pr.url", pr.GetHTMLURL())

	if err := c.UpdateStatusCheck(ctx, org, repo, pr.GetNumber(), promotion); err != nil {
		return fmt.Errorf("failed to update PR status check %d: %w", pr.GetNumber(), err)
	}

	return nil
}
