FROM golang:1.22-bookworm AS build
WORKDIR /src
COPY go.mod ./
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /out/routing ./cmd/routing

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/routing /routing
EXPOSE 8085
USER nonroot:nonroot
ENTRYPOINT ["/routing"]
