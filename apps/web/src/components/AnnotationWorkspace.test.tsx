import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AnnotationWorkspace } from "./AnnotationWorkspace";

const progress = {
  total: 10,
  unreviewed: 9,
  single_review: 0,
  agreed: 1,
  needs_adjudication: 0,
  adjudicated: 0,
};

const item = {
  example: {
    identity: { example_id: "example-1" },
    mandate: { objective_text: "Buy a black laptop bag", constraints: [{ type: "semantic_match" }] },
    cart: {
      total_amount_minor: 5000,
      currency: "USD",
      line_items: [{ description: "Black laptop bag", evidence_text: "Source description" }],
    },
    context: { locale: "en-US", domain: "commerce" },
    provenance: { source_dataset: "ESCI", evidence_origin: "real_public", transformation: "none" },
  },
  completed_reviews: 0,
  needs_adjudication: false,
};

function jsonResponse(value: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(value), { status }));
}

describe("AnnotationWorkspace", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("loads an example and submits a typed review", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    fetchMock
      .mockImplementationOnce(() => jsonResponse(progress))
      .mockImplementationOnce(() => jsonResponse(item))
      .mockImplementationOnce(() => jsonResponse({ status: "recorded" }, 201))
      .mockImplementationOnce(() => jsonResponse({ ...progress, agreed: 2, unreviewed: 8 }))
      .mockImplementationOnce(() => jsonResponse(null));
    const user = userEvent.setup();
    render(<AnnotationWorkspace />);

    await user.type(screen.getByLabelText(/reviewer id/i), "reviewer-a");
    await user.click(screen.getByRole("button", { name: /load next example/i }));
    expect(await screen.findByRole("heading", { name: /buy a black laptop bag/i })).toBeInTheDocument();
    await user.click(screen.getByLabelText("VIOLATION"));
    await user.click(screen.getByLabelText("CONTRADICTION"));
    await user.click(screen.getByLabelText("STEP_UP"));
    await user.click(screen.getByRole("button", { name: /save and continue/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(5));
    const submitted = JSON.parse(String(fetchMock.mock.calls[2][1]?.body));
    expect(submitted).toMatchObject({
      reviewer_id: "reviewer-a",
      deviation: "VIOLATION",
      semantic_label: "CONTRADICTION",
      expected_treatment: "STEP_UP",
    });
  });

  it("shows a useful message when the local annotation service is disabled", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementationOnce(() =>
      jsonResponse({ error: { message: "annotation service is disabled" } }, 404),
    );
    render(<AnnotationWorkspace />);
    expect(await screen.findByRole("alert")).toHaveTextContent("annotation service is disabled");
  });
});
