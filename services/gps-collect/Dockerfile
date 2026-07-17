# Multi-stage: build a static Go binary, ship on distroless-like scratch base.
FROM golang:1.22-bookworm AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /out/gps-collect ./cmd/gps-collect

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/gps-collect /gps-collect
EXPOSE 8081
USER nonroot:nonroot
ENTRYPOINT ["/gps-collect"]
