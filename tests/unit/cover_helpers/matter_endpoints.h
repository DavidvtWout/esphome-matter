#pragma once
#include "runtime.h"
namespace esphome::matter {
class MatterEndpointMappingBase {
 public:
  explicit MatterEndpointMappingBase(uint16_t id) : id_(id) {}
  virtual ~MatterEndpointMappingBase() = default;
  virtual void initialize() {}
  uint16_t endpoint_id() const { return id_; }
 private:
  uint16_t id_;
};
}
