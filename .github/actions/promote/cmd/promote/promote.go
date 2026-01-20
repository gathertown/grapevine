package main

import (
	"context"
	"fmt"
	"os"
	"strconv"

	"github.com/gathertown/corporate-context/.github/actions/promote/internal/promote"
	"github.com/jaredallard/slogext"

	"github.com/urfave/cli/v3"
)

const (
	OrgName  = "gathertown"
	RepoName = "corporate-context"
)

func main() {
	ctx := context.Background()
	log := slogext.New()

	pc := promote.NewClient(ctx)

	cmd := &cli.Command{
		Name:  "promote",
		Usage: "interact with/create promotions",
		Commands: []*cli.Command{
			{
				Name:  "create-pr",
				Usage: "create a PR promoting a given commit to the given environment",
				Arguments: []cli.Argument{
					&cli.StringArg{
						Name: "commit",
					},
					&cli.StringArg{
						Name: "environment",
					},
				},
				Action: func(ctx context.Context, c *cli.Command) error {
					commit := c.StringArg("commit")
					env := promote.Environment(c.StringArg("environment"))
					switch env {
					case promote.EnvironmentProduction, promote.EnvironmentStaging:
					default:
						return fmt.Errorf("unknown environment %s", env)
					}

					prURL, err := pc.CreatePR(ctx, OrgName, RepoName, commit, env)
					if err != nil {
						log.WithError(err).Error("Failed to create PR")
						os.Exit(1)
					}

					log.With("pr.url", prURL).Info("created PR")
					return nil
				},
			},
			{
				Name:  "update-pr",
				Usage: "update a promotion PR's body and status check (github actions only)",
				Arguments: []cli.Argument{
					&cli.IntArg{
						Name: "pull-request-number",
					},
				},
				Action: func(ctx context.Context, c *cli.Command) error {
					prNum := c.IntArg("pull-request-number")
					if prNum == 0 {
						var err error
						prNumStr := os.Getenv("PULL_REQUEST_NUMBER")
						prNum, err = strconv.Atoi(prNumStr)
						if err != nil {
							return fmt.Errorf("failed to parse %q as number: %w", prNumStr, err)
						}
					}

					if err := pc.UpdatePRStatus(ctx, OrgName, RepoName, prNum); err != nil {
						return fmt.Errorf("failed to update PR %d status: %w", prNum, err)
					}

					return nil
				},
			},
			{
				Name:  "create-hotfix-pr",
				Usage: "create a PR to hotfix production",
				Arguments: []cli.Argument{
					&cli.StringArg{
						Name: "commit",
					},
				},
				Action: func(ctx context.Context, c *cli.Command) error {
					commit := c.StringArg("commit")
					if commit == "" {
						return fmt.Errorf("missing required argument 'commit'")
					}

					return pc.CreateHotfixPR(ctx, OrgName, RepoName, commit)
				},
			},
		},
	}

	if err := cmd.Run(ctx, os.Args); err != nil {
		log.WithError(err).Error("failed to run")
		os.Exit(1)
	}
}
